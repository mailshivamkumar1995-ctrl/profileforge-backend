from django.urls import path
from apps.portfolios.views import (
    PublicPortfolioByUsernameView,
    PublicPortfolioBySlugView,
    PublicPortfolioHTMLView,
)

urlpatterns = [
    # JSON data endpoints — designed for headless / Next.js SSR
    path("u/<str:username>/", PublicPortfolioByUsernameView.as_view(), name="public-portfolio-username"),
    path("portfolio/<slug:slug>/", PublicPortfolioBySlugView.as_view(), name="public-portfolio-slug"),
    # Full-HTML render endpoint — future static export / custom domain support
    path("u/<str:username>/render/", PublicPortfolioHTMLView.as_view(), name="public-portfolio-html"),
]
