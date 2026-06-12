samhsa_release_version <- function() {
  getOption("tm.samhsa_release_version", "v0.1.0")
}

samhsa_release_repo <- function() {
  getOption("tm.samhsa_release_repo", "studhall/samhsa-treatment-facility-directories")
}

samhsa_release_asset_url <- function(asset = "facilities.rds") {
  sprintf(
    "https://github.com/%s/releases/download/%s/%s",
    samhsa_release_repo(),
    samhsa_release_version(),
    asset
  )
}

samhsa_release_cache <- function(asset = "facilities.rds") {
  tm_path("data", "public", "samhsa", samhsa_release_version(), asset)
}

download_samhsa_release <- function(asset = "facilities.rds", refresh = FALSE) {
  destination <- samhsa_release_cache(asset)
  if (file.exists(destination) && !refresh) return(destination)
  ensure_dir(dirname(destination))
  utils::download.file(
    samhsa_release_asset_url(asset),
    destination,
    mode = "wb",
    quiet = FALSE
  )
  destination
}

read_samhsa_release <- function(asset = "facilities.rds", refresh = FALSE) {
  path <- download_samhsa_release(asset, refresh = refresh)
  if (grepl("\\.rds$", path, ignore.case = TRUE)) return(readRDS(path))
  readr::read_csv(path, show_col_types = FALSE)
}

run_samhsa_release_validation <- function(refresh = FALSE) {
  facilities <- tryCatch(
    read_samhsa_release("facilities.rds", refresh = refresh),
    error = function(e) {
      warning(
        "Pinned SAMHSA release is unavailable; retaining the legacy local parser fallback. ",
        conditionMessage(e),
        call. = FALSE
      )
      NULL
    }
  )
  if (is.null(facilities)) return(FALSE)

  required <- c(
    "listing_id", "facility_id", "survey_year", "directory_year",
    "state", "county_fips", "latitude", "longitude"
  )
  missing <- setdiff(required, names(facilities))
  if (length(missing) > 0) {
    stop("Pinned SAMHSA release is missing fields: ", paste(missing, collapse = ", "))
  }

  save_rds_safe(facilities, tm_path("data", "processed", "samhsa_facilities_release.rds"))
  write_csv_safe(
    facilities |>
      dplyr::count(directory_year, survey_year, name = "facilities"),
    tm_path("outputs", "diagnostics", "samhsa_release_counts.csv")
  )
  TRUE
}

