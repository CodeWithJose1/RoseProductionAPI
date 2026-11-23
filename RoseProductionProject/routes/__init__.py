"""Flask blueprints: one module per resource plus statistics and GUI."""

from routes.crops import crops_bp
from routes.farms import farms_bp
from routes.forecasts import forecasts_bp
from routes.gui import gui_bp
from routes.harvests import harvests_bp
from routes.lots import lots_bp
from routes.seasons import seasons_bp
from routes.stats import stats_bp
from routes.varieties import varieties_bp

ALL_BLUEPRINTS = (
    farms_bp,
    lots_bp,
    varieties_bp,
    crops_bp,
    seasons_bp,
    harvests_bp,
    forecasts_bp,
    stats_bp,
    gui_bp,
)
