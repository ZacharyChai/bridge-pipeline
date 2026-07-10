output "instance_ip" {
  description = "Public IP of the VM."
  value       = google_compute_instance.vm.network_interface[0].access_config[0].nat_ip
}

output "ssh_command" {
  description = "Ready-to-use SSH command."
  value       = "ssh ${var.ssh_user}@${google_compute_instance.vm.network_interface[0].access_config[0].nat_ip}"
}
