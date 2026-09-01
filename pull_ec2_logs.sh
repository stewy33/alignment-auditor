#!/usr/bin/env bash
# Download experiment logs from the EC2 runner to ./logs/.
# Box IP resolves from: $1  ->  $EC2_BOX  ->  the gitignored .box_ip file.
set -euo pipefail
IP="${1:-${EC2_BOX:-$(cat "$(dirname "$0")/.box_ip" 2>/dev/null || true)}}"
[ -n "$IP" ] || { echo "usage: $0 <box-ip>   (or export EC2_BOX=... / write .box_ip)"; exit 1; }
rsync -az -e "ssh -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new" \
  "ec2-user@${IP}:~/alignment-auditor/logs/" ./logs/
