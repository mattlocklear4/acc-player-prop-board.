#!/usr/bin/env Rscript
# ACC player-game collection diagnostic. Never fabricates rows on fetch failure.
suppressPackageStartupMessages(library(jsonlite))
dir.create('collector', showWarnings=FALSE)
dir.create('collector/output', showWarnings=FALSE, recursive=TRUE)
status <- list(checked_at=format(Sys.time(), '%Y-%m-%dT%H:%M:%SZ', tz='UTC'), season=2027, source='toRvik', status='testing', teams=list(), note='No data verified yet')
write_status <- function() writeLines(toJSON(status, auto_unbox=TRUE, pretty=TRUE, null='null'), 'collector/status.json')
write_status()
if (!requireNamespace('toRvik', quietly=TRUE)) {
  status$status <- 'unavailable'; status$note <- 'toRvik package not installed'; write_status(); quit(status=0)
}
for (team in c('Duke','NC State','Miami')) {
  entry <- list(team=team, advanced_rows=0, box_rows=0, status='unavailable')
  for (kind in c('advanced','box')) {
    fetched <- tryCatch(toRvik::bart_player_game(year=2027, stat=kind, team=team), error=function(e) e)
    if (inherits(fetched,'error')) {
      entry[[paste0(kind,'_error')]] <- substr(conditionMessage(fetched),1,350)
    } else if (is.data.frame(fetched) && nrow(fetched)>0) {
      names(fetched) <- make.names(names(fetched), unique=TRUE)
      # Only 2026-27 regular-season dates; never silently accept stale seasons.
      if ('date' %in% names(fetched)) {
        dt <- suppressWarnings(as.Date(fetched$date))
        fetched <- fetched[!is.na(dt) & dt >= as.Date('2026-11-02') & dt <= as.Date('2027-05-01'),,drop=FALSE]
      }
      if (nrow(fetched)>0) {
        entry[[paste0(kind,'_rows')]] <- nrow(fetched)
        write.csv(fetched, file.path('collector/output',paste0(gsub('[^a-z]','',tolower(team)),'_',kind,'.csv')), row.names=FALSE, na='')
      }
    }
  }
  if (entry$advanced_rows>0 && entry$box_rows>0) entry$status <- 'data_returned'
  else if (entry$advanced_rows>0 || entry$box_rows>0) entry$status <- 'partial'
  status$teams[[length(status$teams)+1]] <- entry
}
if (all(vapply(status$teams,function(x)x$status=='data_returned',logical(1)))) status$status <- 'data_returned'
else if (any(vapply(status$teams,function(x)x$status %in% c('data_returned','partial'),logical(1)))) status$status <- 'partial'
else status$status <- 'unavailable'
status$note <- 'Diagnostic only. Returned data must be validated against the three manually verified games before automatic imports are enabled.'
write_status()
