release_url <- function(
  asset = "facilities.rds",
  version = "v1.1.0"
) {
  sprintf(
    "https://github.com/studhall/samhsa-treatment-facility-directories/releases/download/%s/%s",
    version,
    asset
  )
}

download_release <- function(
  asset = "facilities.rds",
  destination = file.path("data", asset),
  version = "v1.1.0"
) {
  dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
  utils::download.file(
    release_url(asset, version),
    destination,
    mode = "wb"
  )
  destination
}

facilities_path <- download_release()
facilities <- readRDS(facilities_path)
