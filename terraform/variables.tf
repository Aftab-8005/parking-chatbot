variable "postgres_db" {
  default = "parking_db"
}

variable "postgres_user" {
  default = "parking_user"
}

variable "postgres_password" {
  default     = "parking_pass"
  sensitive   = true
}
