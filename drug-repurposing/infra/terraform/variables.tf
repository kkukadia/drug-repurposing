variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type    = string
  default = "drug-repurposing"
}

variable "instance_type" {
  type    = string
  default = "t3.large"
}

variable "key_name" {
  type    = string
  default = null
}

variable "allowed_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]
}

variable "ssh_cidrs" {
  type    = list(string)
  default = []
}
