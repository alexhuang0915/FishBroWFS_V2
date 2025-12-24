
"""NiceGUI 頁面模組"""

from .home import register as register_home
from .new_job import register as register_new_job
from .job import register as register_job
from .results import register as register_results
from .charts import register as register_charts
from .deploy import register as register_deploy
from .history import register as register_history
from .candidates import register as register_candidates
from .wizard import register as register_wizard
from .portfolio import register as register_portfolio
from .run_detail import register as register_run_detail

__all__ = [
    "register_home",
    "register_new_job",
    "register_job",
    "register_results",
    "register_charts",
    "register_deploy",
    "register_history",
    "register_candidates",
    "register_wizard",
    "register_portfolio",
    "register_run_detail",
]


