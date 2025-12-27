
"""NiceGUI 頁面模組"""

from .home import register as register_home
from .new_job import register as register_new_job
from .job import register as register_job
from .results import register as register_results
from .charts import register as register_charts
from .deploy import register as register_deploy
from .artifacts import register as register_artifacts
from .history import register as register_history
from .candidates import register as register_candidates
from .wizard import register as register_wizard
from .portfolio import register as register_portfolio
from .portfolio_governance import register as register_portfolio_governance
from .execution_governance import register as register_execution_governance
from .run_detail import register as register_run_detail
from .settings import register as register_settings
from .status import register as register_status

__all__ = [
    "register_home",
    "register_new_job",
    "register_job",
    "register_results",
    "register_charts",
    "register_deploy",
    "register_artifacts",
    "register_history",
    "register_candidates",
    "register_wizard",
    "register_portfolio",
    "register_portfolio_governance",
    "register_execution_governance",
    "register_run_detail",
    "register_settings",
    "register_status",
]


