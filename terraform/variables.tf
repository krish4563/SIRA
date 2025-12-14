variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
  default     = "tokyo-dynamo-455605-n1"  
}

variable "region" {
  description = "The region to deploy to"
  type        = string
  default     = "asia-south1"
}

variable "backend_service_name" {
  description = "The name of the Backend Cloud Run service"
  type        = string
  default     = "sira-backend"
}

variable "OPENAI_API_KEY" {type = string}
# variable "FRONTEND_ORIGIN" {type = string}
variable "PINECONE_API_KEY" {type = string}
variable "PINECONE_INDEX" {type = string}
variable "SERPAPI_KEY" {type = string}
variable "BRAVE_KEY" {type = string}
variable "SUMMARIZER_MODEL" {type = string}
variable "SUPABASE_URL" {type = string}
variable "SUPABASE_SERVICE_ROLE_KEY" {type = string}
variable "SMTP_HOST" {type = string}
variable "SMTP_PORT" {type = string}
variable "SMTP_USER" {type = string}
variable "SMTP_PASSWORD" {type = string}
variable "SMTP_FROM_EMAIL" {type = string}
variable "SMTP_FROM_NAME" {type = string}
variable "TWITTER_BEARER_TOKEN" {type = string}
variable "OPENWEATHER_API_KEY" {type = string}