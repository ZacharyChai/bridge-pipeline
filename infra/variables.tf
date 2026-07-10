variable "project_id" {
  type        = string
  description = "GCP project ID to deploy into."
}

variable "region" {
  type        = string
  description = "GCP region."
  default     = "us-central1" # Always Free tier eligible
}

variable "zone" {
  type        = string
  description = "GCP zone."
  default     = "us-central1-a"
}

variable "name" {
  type        = string
  description = "Base name for resources."
  default     = "bridge-pipeline"
}

variable "machine_type" {
  type        = string
  description = "Instance size. e2-micro is Always-Free eligible but only 1GB; e2-small (2GB) is roomier for Postgres."
  default     = "e2-small"
}

variable "image" {
  type        = string
  description = "Boot image."
  default     = "debian-cloud/debian-12"
}

variable "disk_size_gb" {
  type        = number
  description = "Boot disk size in GB."
  default     = 20
}

variable "ssh_user" {
  type        = string
  description = "Non-root login user created on the box."
  default     = "deploy"
}

variable "ssh_pubkey_path" {
  type        = string
  description = "Path to your SSH public key (added to the box for key-only login)."
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_source_ranges" {
  type        = list(string)
  description = "CIDRs allowed to reach SSH. Required — set to YOUR_IP/32, not 0.0.0.0/0. Find your IP with: curl ifconfig.me"
}
