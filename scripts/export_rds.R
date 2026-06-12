args <- commandArgs(trailingOnly = TRUE)
release_dir <- if (length(args) >= 1) args[[1]] else "release"

inputs <- c(
  facilities = "facilities.csv.gz",
  facility_services = "facility_services.csv.gz",
  service_availability = "service_availability.csv",
  facility_entities = "facility_entities.csv",
  geocoding_results = "geocoding_results.csv"
)

for (name in names(inputs)) {
  input <- file.path(release_dir, inputs[[name]])
  if (!file.exists(input)) {
    if (name == "geocoding_results") next
    stop("Missing release input: ", input)
  }
  data <- read.csv(input, stringsAsFactors = FALSE, check.names = FALSE)
  saveRDS(data, file.path(release_dir, paste0(name, ".rds")), compress = "xz")
  message("Wrote ", file.path(release_dir, paste0(name, ".rds")))
}

