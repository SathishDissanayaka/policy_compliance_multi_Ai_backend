from utils.supabase_client import supabase


def get_policy_contexts():
    """
    Fetch all policy contexts from Supabase table `policy_contexts`.
    Returns a list of dictionaries.
    """
    response = supabase.table("policy_contexts").select("*").execute()

    # Normalise the response to extract data in a few common shapes
    def _extract_data(resp):
        # Preferred: object with .data attribute (newer client wrappers)
        if hasattr(resp, "data"):
            return resp.data
        # If it's a dict-like response
        if isinstance(resp, dict):
            return resp.get("data") or resp.get("body") or resp.get("result") or []
        # If it's a sequence like (data, count) or (data, status)
        if isinstance(resp, (list, tuple)) and len(resp) > 0:
            return resp[0]
        # Unknown shape -> return empty
        return []

    data = _extract_data(response)

    # Check for obvious HTTP-style errors on some clients
    status = None
    if hasattr(response, "status_code"):
        status = getattr(response, "status_code")
    elif isinstance(response, dict):
        status = response.get("status_code") or response.get("status")

    try:
        if status and int(status) >= 400:
            print("Error fetching policy contexts, status:", status)
            return []
    except Exception:
        # ignore any odd status shapes
        pass

    if not data:
        # If nothing returned, log a small diagnostic for easier debugging
        try:
            # Try to surface any message/error fields
            err = getattr(response, "error", None) or (response.get("error") if isinstance(response, dict) else None)
        except Exception:
            err = None

        if err:
            print("Error fetching policy contexts:", err)
        else:
            print("Warning: policy_contexts query returned no rows or unexpected response shape")

        return []

    return data
