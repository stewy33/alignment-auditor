#!/usr/bin/env python3
"""Run an `inspect eval` on a Daytona docker-in-docker sandbox instead of locally.

Offloads a whole eval cell to a fresh cloud sandbox that runs its own Docker engine,
so the eval's `docker compose` sandboxes run nested inside Daytona — freeing the local
box (e.g. when an overnight batch is already using it) and giving real cross-cell
parallelism (launch one of these per cell).

Usage (normally invoked via a run script's `--daytona` flag):

    uv run python daytona_eval.py \
        --local-log-dir logs/.../step3_exploit_share/react__glm52__subtle \
        -- inspect eval <task.py> --model ... -T ... --epochs 8 --max-samples 2 \
           --display plain

Everything after `--` is the exact inspect command to run INSIDE the sandbox (WITHOUT a
--log-dir; this runner appends one pointing at a sandbox path and downloads the produced
.eval files back into --local-log-dir). Requires DAYTONA_API_KEY and the model provider
key(s) (OPENROUTER_API_KEY / ANTHROPIC_API_KEY) in the local environment.
"""
import argparse
import io
import os
import sys
import tarfile
import time

from daytona import CreateSandboxFromImageParams, Daytona, Image

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
REPO_NAME = os.path.basename(REPO_ROOT)
SANDBOX_WORK = "/work"
SANDBOX_REPO = f"{SANDBOX_WORK}/{REPO_NAME}"
SANDBOX_LOGDIR = f"{SANDBOX_WORK}/eval-logs"
EXCLUDE_DIRS = {".git", ".venv", "logs", "node_modules", "__pycache__", ".mypy_cache",
                ".pytest_cache", ".ruff_cache"}

# Image: python + docker engine + uv. Daytona builds this declaratively (cached by content).
IMAGE = Image.base("python:3.12").dockerfile_commands([
    "RUN apt-get update && apt-get install -y --no-install-recommends "
    "curl ca-certificates git iptables && rm -rf /var/lib/apt/lists/*",
    "RUN curl -fsSL https://get.docker.com | sh",
    "RUN pip install --no-cache-dir uv",
])


def log(*a):
    print(*a, flush=True)


def make_repo_tar() -> bytes:
    """Tar the repo source, excluding heavy/generated dirs (see EXCLUDE_DIRS)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        def filt(ti: tarfile.TarInfo):
            parts = set(ti.name.split("/"))
            if parts & EXCLUDE_DIRS:
                return None
            return ti
        tf.add(REPO_ROOT, arcname=REPO_NAME, filter=filt)
    return buf.getvalue()


def sh(sb, cmd, cwd=None, env=None, timeout=600, check=True, quiet=False):
    """Exec a command in the sandbox; print and optionally assert success."""
    if not quiet:
        log(f"\n$ {cmd}")
    r = sb.process.exec(cmd, cwd=cwd, env=env, timeout=timeout)
    code = getattr(r, "exit_code", None)
    out = getattr(r, "result", "") or ""
    if not quiet:
        log(out[-4000:] if out else "(no output)")
    if check and code != 0:
        raise RuntimeError(f"command failed (exit {code}): {cmd}")
    return code, out


def start_dockerd(sb):
    log(">> starting dockerd in sandbox ...")
    sb.process.exec(
        "nohup dockerd >/var/log/dockerd.log 2>&1 & echo started", timeout=30)
    for i in range(30):
        code, _ = sh(sb, "docker info >/dev/null 2>&1 && echo UP || echo DOWN",
                     timeout=30, check=False, quiet=True)
        c2, out = sh(sb, "docker info >/dev/null 2>&1; echo $?", timeout=30,
                     check=False, quiet=True)
        if out.strip().endswith("0"):
            log(f">> dockerd up after ~{i * 2}s")
            return
        time.sleep(2)
    sh(sb, "tail -30 /var/log/dockerd.log", check=False)
    raise RuntimeError("dockerd did not become ready")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local-log-dir", required=True,
                    help="local dir to download the produced .eval logs into")
    ap.add_argument("--keep", action="store_true", help="do not delete the sandbox at the end")
    ap.add_argument("--eval-timeout", type=int, default=5400)
    ap.add_argument("--cpu", type=int, default=None, help="sandbox vCPUs (Daytona Resources)")
    ap.add_argument("--memory", type=int, default=None, help="sandbox RAM in GiB")
    ap.add_argument("--disk", type=int, default=None, help="sandbox disk in GiB")
    ap.add_argument("inspect_cmd", nargs=argparse.REMAINDER,
                    help="everything after `--`: the inspect command to run in-sandbox")
    args = ap.parse_args()

    cmd = args.inspect_cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        ap.error("no inspect command given after `--`")

    keys = {k: os.environ[k] for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")
            if os.environ.get(k)}
    if not keys:
        ap.error("no model provider key (OPENROUTER_API_KEY / ANTHROPIC_API_KEY) in env")
    if not os.environ.get("DAYTONA_API_KEY"):
        ap.error("DAYTONA_API_KEY not set")

    os.makedirs(args.local_log_dir, exist_ok=True)
    inspect_cmd = " ".join(cmd) + f" --log-dir {SANDBOX_LOGDIR}"

    d = Daytona()
    sb = None
    try:
        log(">> creating DinD sandbox (building image if needed; first run is slow) ...")
        resources = None
        if any([args.cpu, args.memory, args.disk]):
            from daytona import Resources
            resources = Resources(cpu=args.cpu, memory=args.memory, disk=args.disk)
            log(f">> requesting resources: cpu={args.cpu} memory={args.memory}GiB disk={args.disk}GiB")
        sb = d.create(CreateSandboxFromImageParams(
            image=IMAGE, env_vars=keys, ephemeral=True, ttl_minutes=180,
            resources=resources,
        ), timeout=1200)
        log(">> sandbox:", getattr(sb, "id", "?"))

        start_dockerd(sb)

        log(">> uploading repo tarball ...")
        tar = make_repo_tar()
        log(f"   ({len(tar) // 1024} KiB)")
        sb.fs.upload_file(tar, f"{SANDBOX_WORK}/repo.tgz")
        sh(sb, f"mkdir -p {SANDBOX_WORK} {SANDBOX_LOGDIR} && "
              f"tar xzf {SANDBOX_WORK}/repo.tgz -C {SANDBOX_WORK}")

        log(">> installing deps with uv ...")
        sh(sb, "uv sync", cwd=SANDBOX_REPO, timeout=1800)

        log(">> running eval in sandbox:")
        log("   " + inspect_cmd)
        code, _ = sh(sb, "uv run " + inspect_cmd, cwd=SANDBOX_REPO,
                     env=keys, timeout=args.eval_timeout, check=False)
        log(f">> eval exited {code}")

        log(">> downloading .eval logs ...")
        _, listing = sh(sb, f"ls -1 {SANDBOX_LOGDIR} 2>/dev/null || true",
                        check=False, quiet=True)
        got = 0
        for name in [n for n in listing.splitlines() if n.strip().endswith(".eval")]:
            data = sb.fs.download_file(f"{SANDBOX_LOGDIR}/{name}")
            if data:
                with open(os.path.join(args.local_log_dir, name), "wb") as f:
                    f.write(data)
                got += 1
                log(f"   downloaded {name} ({len(data) // 1024} KiB)")
        log(f">> downloaded {got} .eval file(s) -> {args.local_log_dir}")
        if code != 0 or got == 0:
            sys.exit(1)
    finally:
        if sb is not None and not args.keep:
            try:
                log(">> deleting sandbox")
                d.delete(sb)
            except Exception as e:
                log("!! delete failed:", repr(e))


if __name__ == "__main__":
    main()
