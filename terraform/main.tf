# ---------------------------------------------------
# 1. Artifact Registry (Storage for Docker Images)
# ---------------------------------------------------
resource "google_artifact_registry_repository" "sira_repo" {
  location      = var.region
  repository_id = "sira-repo"
  description   = "Docker repository for SIRA Application"
  format        = "DOCKER"
}

# ---------------------------------------------------
# 2. Cloud Run Service (The Backend Server)
# ---------------------------------------------------
resource "google_cloud_run_service" "backend" {
  name     = var.backend_service_name
  location = var.region

  template {
    spec {
      containers {
        # This points to the image we will upload later
        image = "${var.region}-docker.pkg.dev/${var.project_id}/sira-repo/${var.backend_service_name}:latest"
        
        resources {
          limits = {
            memory = "512Mi"
            cpu    = "1"
          }
        }
        
        ports {
          container_port = 8080
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

# ---------------------------------------------------
# 3. Public Access (Make Backend accessible to Frontend)
# ---------------------------------------------------
data "google_iam_policy" "noauth" {
  binding {
    role = "roles/run.invoker"
    members = [
      "allUsers",
    ]
  }
}

resource "google_cloud_run_service_iam_policy" "noauth" {
  location    = google_cloud_run_service.backend.location
  project     = google_cloud_run_service.backend.project
  service     = google_cloud_run_service.backend.name
  policy_data = data.google_iam_policy.noauth.policy_data
}