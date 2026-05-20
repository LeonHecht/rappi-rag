from fastapi import APIRouter, Depends, HTTPException
from backend.app.dependencies import get_current_user
from backend.app.services.auth import UserData, get_supabase
from backend.app.core.config import settings

router = APIRouter()

try:
    import stripe  # type: ignore
except Exception:
    stripe = None  # gracefully handle missing dependency


@router.post("/billing/portal")
def create_billing_portal_session(user: UserData = Depends(get_current_user)):
    """Create (or reuse) a Stripe customer and return a Billing Portal URL.

    Uses public.payment_accounts as the source of truth for the Stripe customer id
    (provider_customer_id), keyed by (user_id, provider='stripe').
    """
    if stripe is None:
        raise HTTPException(status_code=501, detail="Stripe SDK not installed on server")
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=501, detail="Stripe not configured (missing STRIPE_SECRET_KEY)")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Determine return URL
    return_url = (
        settings.BILLING_RETURN_URL
        or (settings.FRONTEND_BASE_URL + "/settings/billing" if settings.FRONTEND_BASE_URL else None)
        or "http://localhost:5173/settings/billing"
    )

    # Ensure we have a payment account row or create one
    sb = get_supabase()
    acct_resp = (
        sb.table("payment_accounts")
        .select("user_id, provider, provider_customer_id")
        .eq("user_id", user.user_id)
        .eq("provider", "stripe")
        .limit(1)
        .execute()
    )
    account = acct_resp.data[0] if acct_resp.data else None
    customer_id = account.get("provider_customer_id") if account else None

    # Create Stripe customer if needed
    if not customer_id:
        try:
            customer = stripe.Customer.create(
                email=user.username,
                name=f"{user.first_name} {user.last_name}".strip() or user.username,
                metadata={"app": settings.APP_NAME, "email": user.username},
            )
            customer_id = customer["id"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create Stripe customer: {e}")

        # Upsert into payment_accounts (PK is user_id)
        try:
            if account:
                sb.table("payment_accounts").update({"provider_customer_id": customer_id}).eq("user_id", account["user_id"]).eq("provider", "stripe").execute()
            else:
                sb.table("payment_accounts").upsert(
                    {
                        "user_id": user.user_id,
                        "provider": "stripe",
                        "provider_customer_id": customer_id,
                        "subscription_tier": "free",
                    },
                    on_conflict="user_id",
                ).execute()
        except Exception as e:
            # Not fatal to portal creation, but we log it
            print(f"⚠️ Failed to upsert provider_customer_id in payment_accounts: {e}")

    # Create a Billing Portal session
    if not customer_id:
        raise HTTPException(status_code=500, detail="Stripe customer not available")

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create billing portal session: {e}")

    return {"url": session["url"]}


@router.get("/billing/status")
def get_billing_status(user: UserData = Depends(get_current_user)):
    """Return the user's current subscription tier as tracked in payment_accounts.

    Response shape: { "subscription_tier": "free|pro|team|enterprise", "provider": "stripe" }
    Defaults to tier "free" if no payment account exists.
    """
    try:
        sb = get_supabase()
        resp = (
            sb.table("payment_accounts")
            .select("subscription_tier, provider")
            .eq("user_id", user.user_id)
            .eq("provider", "stripe")
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            tier = row.get("subscription_tier") or "free"
            provider = row.get("provider") or "stripe"
        else:
            tier = "free"
            provider = "stripe"
        return {"subscription_tier": tier, "provider": provider}
    except Exception as e:
        # On error, don't block UI; degrade gracefully
        print(f"get_billing_status error: {e}")
        return {"subscription_tier": "free", "provider": "stripe"}
