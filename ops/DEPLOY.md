# ASTA Deployment Runbook

Deploying ASTA is designed to be fully automated and idempotent. Never edit files via SSH on the server. All changes must be pushed to git.

## Runbook (5 Commands)

1. SSH into the Oracle Cloud instance:
   ```bash
   ssh ubuntu@<instance-ip>
   ```

2. Navigate to the ASTA directory:
   ```bash
   cd ~/ASTA
   ```

3. Pull the latest changes from the master branch:
   ```bash
   git pull origin master
   ```

4. Navigate to the ops directory:
   ```bash
   cd ops
   ```

5. Rebuild and restart the containers in detached mode:
   ```bash
   docker compose up -d --build
   ```

That's it. The new containers will come online and healthchecks will verify their status.
