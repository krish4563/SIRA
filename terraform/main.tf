# 1. Artifact Registry Repository
resource "google_artifact_registry_repository" "sira_repo" {
  location      = var.region
  repository_id = "sira-repo"
  description   = "Docker repository for SIRA Application"
  format        = "DOCKER"
}

# 2. Cloud Run Service (The Backend Server)
resource "google_cloud_run_service" "backend" {
  name     = var.backend_service_name
  location = var.region

  template {
    spec {
      containers {
        image = "us-docker.pkg.dev/cloudrun/container/hello"

        resources {
          limits = {
            memory = "1Gi"
            cpu    = "1"
          }
        }

        ports {
          container_port = 8080
        }

        # --- Environment Variables ---
        env {
          name  = "OPENAI_API_KEY"
          value = var.OPENAI_API_KEY
        }
        # env {
        #   name  = "FRONTEND_ORIGIN"
        #   value = var.FRONTEND_ORIGIN
        # }
        env {
          name  = "PINECONE_API_KEY"
          value = var.PINECONE_API_KEY
        }
        env {
          name  = "PINECONE_INDEX"
          value = var.PINECONE_INDEX
        }
        env {
          name  = "SERPAPI_KEY"
          value = var.SERPAPI_KEY
        }
        env {
          name  = "BRAVE_KEY"
          value = var.BRAVE_KEY
        }
        env {
          name  = "SUMMARIZER_MODEL"
          value = var.SUMMARIZER_MODEL
        }
        env {
          name  = "SUPABASE_URL"
          value = var.SUPABASE_URL
        }
        env {
          name  = "SUPABASE_SERVICE_ROLE_KEY"
          value = var.SUPABASE_SERVICE_ROLE_KEY
        }
        env {
          name  = "SMTP_HOST"
          value = var.SMTP_HOST
        }
        env {
          name  = "SMTP_PORT"
          value = var.SMTP_PORT
        }
        env {
          name  = "SMTP_USER"
          value = var.SMTP_USER
        }
        env {
          name  = "SMTP_PASSWORD"
          value = var.SMTP_PASSWORD
        }
        env {
          name  = "SMTP_FROM_EMAIL"
          value = var.SMTP_FROM_EMAIL
        }
        env {
          name  = "SMTP_FROM_NAME"
          value = var.SMTP_FROM_NAME
        }
        env {
          name  = "TWITTER_BEARER_TOKEN"
          value = var.TWITTER_BEARER_TOKEN
        }
        env {
          name  = "OPENWEATHER_API_KEY"
          value = var.OPENWEATHER_API_KEY
        }
      }
    }
  }

  # "Once created, DO NOT change the image back to 'hello-world' even if I run terraform apply again."
  lifecycle {
    ignore_changes = [
      template[0].spec[0].containers[0].image,
      traffic
    ]
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

# 3. Public Access
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