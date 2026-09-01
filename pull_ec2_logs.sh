#!/usr/bin/env bash
# Download run logs from the EC2 box to ./logs/
rsync -az -e "ssh -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new" \
  ec2-user@54.162.84.40:~/alignment-auditor/logs/ ./logs/
