# A minimal, hardened box: one VPC, SSH-only ingress, one VM that bootstraps
# itself (non-root user, key-only SSH, ufw, Docker) via the startup script.

resource "google_compute_network" "vpc" {
  name                    = "${var.name}-vpc"
  auto_create_subnetworks = true
}

# Only SSH inbound, and only from the CIDRs you allow. Everything else is denied
# by GCP's implied-deny; egress stays open so the box can reach FRED + pull images.
resource "google_compute_firewall" "ssh" {
  name          = "${var.name}-allow-ssh"
  network       = google_compute_network.vpc.name
  direction     = "INGRESS"
  source_ranges = var.ssh_source_ranges
  target_tags   = ["bridge"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_instance" "vm" {
  name         = var.name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["bridge"]

  boot_disk {
    initialize_params {
      image = var.image
      size  = var.disk_size_gb
    }
  }

  network_interface {
    network = google_compute_network.vpc.name
    access_config {} # ephemeral public IP
  }

  metadata = {
    # Key-only login for the non-root user; disable OS Login so this key is used.
    ssh-keys       = "${var.ssh_user}:${trimspace(file(pathexpand(var.ssh_pubkey_path)))}"
    enable-oslogin = "FALSE"
    # Read by bootstrap.sh so the hardened user matches var.ssh_user.
    deploy-user = var.ssh_user
  }

  # Runs as root on first boot: hardening + Docker install.
  metadata_startup_script = file("${path.module}/bootstrap.sh")
}
