import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="portfolio",
    name="portfolio.rebuild",
)
def rebuild_portfolio(self, user_id: str):
    """Rebuild and publish portfolio static site for a user."""
    try:
        from django.contrib.auth import get_user_model
        from apps.portfolios.models import Portfolio
        from apps.portfolios.services import PortfolioService

        User = get_user_model()
        user = User.objects.get(id=user_id)

        portfolio = Portfolio.objects.filter(user=user, is_published=True).first()
        if portfolio:
            PortfolioService.regenerate(portfolio)
            logger.info("Portfolio rebuilt", extra={"portfolio_id": str(portfolio.id)})

    except Exception as exc:
        logger.error("Failed to rebuild portfolio", exc_info=True)
        raise self.retry(exc=exc)
