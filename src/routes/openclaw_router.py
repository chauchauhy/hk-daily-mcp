## pylint disable=W0613,W1203,E1136,W0718
import logging

from fastapi import APIRouter

from utils import daily_summary_service

router = APIRouter(prefix="/openclaw_router", tags=["openclaw_router"])
logger = logging.getLogger(__name__)


@router.get("/")
async def get_hko_router():
    return {"message": "This is the openclaw_router endpoint"}


@router.get("/dailySummary/{lang}/{keyword}/{address}/{router}")
async def get_daily_summary(lang: str, keyword: str, address: str, router: str):
    logger.info(f"Fetching daily summary for language: {lang}, address: {address}, router: {router}, keyword: {keyword}...")
    return await daily_summary_service.get_daily_summary(lang, keyword, address, router)
