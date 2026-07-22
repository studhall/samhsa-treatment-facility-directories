args <- commandArgs(trailingOnly = TRUE)
release_dir <- if (length(args) >= 1) args[[1]] else "release"

inputs <- c(
  facilities = "facilities.csv.gz",
  facility_services = "facility_services.csv.gz",
  service_availability = "service_availability.csv",
  facility_entities = "facility_entities.csv",
  geocoding_results = "geocoding_results.csv"
)
required <- c("facilities", "facility_services", "service_availability")

read_release <- function(path) {
  if (requireNamespace("data.table", quietly = TRUE)) {
    return(as.data.frame(data.table::fread(path, showProgress = FALSE)))
  }
  read.csv(path, stringsAsFactors = FALSE, check.names = FALSE)
}

for (name in names(inputs)) {
  input <- file.path(release_dir, inputs[[name]])
  if (!file.exists(input)) {
    if (name %in% required) stop("Missing release input: ", input)
    next
  }
  data <- read_release(input)
  output <- file.path(release_dir, paste0(name, ".rds"))
  saveRDS(data, output, compress = "xz")
  message("Wrote ", output)
}
