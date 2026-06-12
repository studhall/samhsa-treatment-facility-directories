args_all <- commandArgs(trailingOnly = FALSE)
file_arg <- args_all[grepl("^--file=", args_all)]
root <- if (length(file_arg) > 0) dirname(normalizePath(sub("^--file=", "", file_arg[1]), winslash = "/")) else getwd()
setwd(root)
options(tm.root = root)

source("R/utils/packages.R")
source("R/utils/paths.R")
source("R/utils/io.R")
source("R/utils/analysis_helpers.R")
source("R/utils/panel_checks.R")

load_config_if_present()
ensure_standard_dirs()

script_files <- c(
  "R/00_samhsa_release.R",
  "R/01_inventory.R",
  "R/02_cbp_audit.R",
  "R/03_build_analysis_panels.R",
  "R/03b_descriptive_outputs.R",
  "R/04_estimate_twfe.R",
  "R/05_design_diagnostics.R",
  "R/06_serial_correlation.R",
  "R/07_nssats_extract_validate.R",
  "R/08_distance_access.R",
  "R/09_monte_carlo_attenuation.R",
  "R/10_public_use_workflow.R",
  "R/12_results_replication_extension.R",
  "R/11_validate_outputs.R"
)
invisible(lapply(script_files, source))

full_nssats <- "--full-nssats" %in% commandArgs(trailingOnly = TRUE)
reparse_all_nssats <- "--reparse-all-nssats" %in% commandArgs(trailingOnly = TRUE)
legacy_nssats <- "--legacy-nssats" %in% commandArgs(trailingOnly = TRUE)
refresh_samhsa_release <- "--refresh-samhsa-release" %in% commandArgs(trailingOnly = TRUE)

run_preferred_nssats <- function() {
  if (!legacy_nssats) {
    used_release <- run_samhsa_release_validation(refresh = refresh_samhsa_release)
    if (used_release) return(invisible(TRUE))
  }
  run_nssats_validation(
    extract_empty_years = full_nssats,
    reparse_all_years = reparse_all_nssats,
    prefer_reparsed = TRUE
  )
}

steps <- list(
  inventory = function() run_inventory(),
  cbp_audit = function() run_cbp_audit(),
  panels = function() run_build_analysis_panels(),
  twfe = function() run_twfe_estimates(),
  design = function() run_design_diagnostics(),
  serial = function() run_serial_correlation_diagnostics(),
  nssats = function() run_preferred_nssats(),
  descriptives = function() run_descriptive_outputs(),
  distance = function() run_distance_access(),
  monte_carlo = function() run_monte_carlo_attenuation(),
  public_use = function() run_public_use_workflow(),
  results = function() run_replication_extension_results(),
  validate_outputs = function() run_validate_outputs()
)

log_path <- tm_path("outputs", "logs", "run_all.log")
write_lines_safe(paste0("Run started: ", Sys.time()), log_path)

for (nm in names(steps)) {
  message("\n==> Running step: ", nm)
  cat(paste0("\n==> Running step: ", nm, " at ", Sys.time(), "\n"), file = log_path, append = TRUE)
  t0 <- Sys.time()
  tryCatch(
    {
      steps[[nm]]()
      elapsed <- round(as.numeric(difftime(Sys.time(), t0, units = "secs")), 2)
      cat(paste0("OK: ", nm, " (", elapsed, " seconds)\n"), file = log_path, append = TRUE)
    },
    error = function(e) {
      cat(paste0("FAILED: ", nm, "\n", conditionMessage(e), "\n"), file = log_path, append = TRUE)
      stop(e)
    }
  )
}

message("\nClean replication run complete. See outputs/diagnostics and outputs/tables.")
cat(paste0("\nRun completed: ", Sys.time(), "\n"), file = log_path, append = TRUE)
