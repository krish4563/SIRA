variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
  default     = "tokyo-dynamo-455605-n1"  # I added your project ID here
}

variable "region" {
  description = "The region to deploy to"
  type        = string
  default     = "asia-south1" # Mumbai
}

variable "backend_service_name" {
  description = "The name of the Backend Cloud Run service"
  type        = string
  default     = "sira-backend"
}