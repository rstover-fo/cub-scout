# src/api/routers/admin.py
from fastapi import APIRouter, Query, HTTPException
from ..storage.db import get_connection, get_pending_links, update_pending_link_status, get_scouting_player
from ..processing.aggregation import refresh_player_sentiment
from ..api.models import PendingLink, LinkReviewUpdate

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/pending-links", response_model=list[PendingLink])
async def list_pending_links(
    status: str = Query("pending", enum=["pending", "approved", "rejected"]),
    limit: int = Query(50, ge=1, le=200),
):
    """List pending player links for manual review."""
    async with get_connection() as conn:
        links = await get_pending_links(conn, status=status, limit=limit)
        return [PendingLink(**link) for link in links]

@router.post("/pending-links/{link_id}/review")
async def review_link(link_id: int, review: LinkReviewUpdate):
    """Approve or reject a pending player link. 
    
    If approved, automatically triggers a sentiment refresh for the associated player.
    """
    async with get_connection() as conn:
        # Get link info before updating so we know who the player is
        cur = conn.cursor()
        await cur.execute("SELECT candidate_roster_id FROM scouting.pending_links WHERE id = %s", (link_id,))
        row = await cur.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Link not found")
            
        player_id = row[0]
        
        # Update status
        await update_pending_link_status(conn, link_id, review.status)
        
        refresh_result = None
        if review.status == "approved" and player_id:
            # TRIGGER THE ORCHESTRATION HOOK
            try:
                refresh_result = await refresh_player_sentiment(player_id)
            except Exception as e:
                # Log but don't fail the whole request
                print(f"Failed to refresh sentiment for player {player_id}: {e}")

        return {
            "status": "updated", 
            "id": link_id, 
            "new_status": review.status,
            "sentiment_refreshed": refresh_result is not None,
            "new_grade": refresh_result.get("composite_grade") if refresh_result else None
        }
