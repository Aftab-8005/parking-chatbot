terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

resource "docker_network" "parking_net" {
  name = "parking-net"
}

resource "docker_volume" "qdrant_data" {
  name = "parking_qdrant_data"
}

resource "docker_volume" "postgres_data" {
  name = "parking_postgres_data"
}

resource "docker_image" "qdrant" {
  name = "qdrant/qdrant:v1.12.4"
}

resource "docker_image" "postgres" {
  name = "postgres:16-alpine"
}

resource "docker_container" "qdrant" {
  name  = "parking-qdrant"
  image = docker_image.qdrant.image_id

  networks_advanced {
    name = docker_network.parking_net.name
  }

  ports {
    internal = 6333
    external = 6333
  }
  ports {
    internal = 6334
    external = 6334
  }

  volumes {
    volume_name    = docker_volume.qdrant_data.name
    container_path = "/qdrant/storage"
  }
}

resource "docker_container" "postgres" {
  name  = "parking-postgres"
  image = docker_image.postgres.image_id

  networks_advanced {
    name = docker_network.parking_net.name
  }

  env = [
    "POSTGRES_DB=${var.postgres_db}",
    "POSTGRES_USER=${var.postgres_user}",
    "POSTGRES_PASSWORD=${var.postgres_password}",
  ]

  ports {
    internal = 5432
    external = 5433
  }

  volumes {
    volume_name    = docker_volume.postgres_data.name
    container_path = "/var/lib/postgresql/data"
  }
}
