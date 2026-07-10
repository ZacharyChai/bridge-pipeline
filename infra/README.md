# infra/ — Terraform (GCP)

Provisions a hardened Debian VM on Google Compute Engine with SSH-only ingress,
and bootstraps it (non-root user, key-only SSH, `ufw`, Docker) via
[`bootstrap.sh`](bootstrap.sh).

## One-time prerequisites

1. **Tools:** Terraform (in `~/.local/bin`) and the `gcloud` CLI.
   ```bash
   brew install --cask google-cloud-sdk    # if gcloud isn't installed
   export PATH="$HOME/.local/bin:$PATH"     # so `terraform` is found
   ```
2. **GCP project:** create one (or pick an existing ID) and note the project ID.
3. **Enable the Compute Engine API:**
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   gcloud services enable compute.googleapis.com
   ```
4. **Auth for Terraform (Application Default Credentials):**
   ```bash
   gcloud auth application-default login
   ```
5. **SSH key** (if you don't have one):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
   ```

## Provision

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # set project_id + ssh_source_ranges (YOUR_IP/32)
terraform init
terraform plan       # review — no changes made yet
terraform apply      # creates the box (~$13/mo for e2-small; e2-micro is Always-Free)
```

Then:

```bash
terraform output ssh_command      # ssh deploy@<ip>
# on the box, confirm hardening + Docker:
#   sudo ufw status          -> Status: active, 22 (OpenSSH) allowed
#   docker --version
#   sudo tail -n 40 /var/log/bootstrap.log
```

## Tear down

```bash
terraform destroy
```

Keeping the box running is the Linux-ops rep — don't destroy it until you've
stopped using it as a resume talking point.
