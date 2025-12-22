
"""NiceGUI 頁面模組"""

from .home import register as register_home
from .new_job import register as register_new_job
from .job import register as register_job
from .results import register as register_results
from .charts import register as register_charts
from .deploy import register as register_deploy

__all__ = [
    "register_home",
    "register_new_job",
    "register_job",
    "register_results",
    "register_charts",
    "register_deploy",
]


