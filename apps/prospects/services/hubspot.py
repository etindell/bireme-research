import os
import logging
from django.utils import timezone

try:
    from hubspot import HubSpot
    from hubspot.crm.contacts import SimplePublicObjectInputForCreate, ApiException
    from hubspot.crm.objects.notes import SimplePublicObjectInputForCreate as NoteInput
    HUBSPOT_AVAILABLE = True
except ImportError:
    HUBSPOT_AVAILABLE = False

logger = logging.getLogger(__name__)

def get_hubspot_client():
    if not HUBSPOT_AVAILABLE:
        logger.error("hubspot-api-client not installed.")
        return None
    token = os.environ.get('HUBSPOT_ACCESS_TOKEN')
    if not token:
        logger.warning("HUBSPOT_ACCESS_TOKEN not found in environment.")
        return None
    return HubSpot(access_token=token)

def sync_prospect_to_hubspot(prospect):
    """Create or update contact in HubSpot and return the HubSpot ID."""
    if not HUBSPOT_AVAILABLE:
        return None
    client = get_hubspot_client()
    if not client:
        return None

    properties = {
        "email": prospect.email,
        "firstname": prospect.first_name,
        "lastname": prospect.last_name,
        "company": prospect.company_name,
        "phone": prospect.phone,
        "hs_lead_status": prospect.status.lower() # HubSpot expects lowercase internal values
    }

    try:
        if prospect.hubspot_id:
            # Update existing
            client.crm.contacts.basic_api.update(
                contact_id=prospect.hubspot_id,
                simple_public_object_input=SimplePublicObjectInputForCreate(properties=properties)
            )
            hs_id = prospect.hubspot_id
        else:
            # Check if contact exists by email first to avoid duplicates
            try:
                existing = client.crm.contacts.basic_api.get_by_id(
                    contact_id=prospect.email,
                    id_property="email"
                )
                hs_id = existing.id
                # Update it
                client.crm.contacts.basic_api.update(
                    contact_id=hs_id,
                    simple_public_object_input=SimplePublicObjectInputForCreate(properties=properties)
                )
            except ApiException as e:
                if e.status == 404:
                    # Create new
                    create_res = client.crm.contacts.basic_api.create(
                        simple_public_object_input=SimplePublicObjectInputForCreate(properties=properties)
                    )
                    hs_id = create_res.id
                else:
                    raise e

        prospect.hubspot_id = hs_id
        prospect.last_synced_at = timezone.now()
        prospect.sync_status = 'Success'
        prospect.save(update_fields=['hubspot_id', 'last_synced_at', 'sync_status'])
        return hs_id

    except ApiException as e:
        logger.error(f"HubSpot API error: {e}")
        prospect.sync_status = f'Error: {e.status}'
        prospect.save(update_fields=['sync_status'])
        return None

def sync_note_to_hubspot(prospect_note):
    """Add a note to the contact in HubSpot."""
    if not HUBSPOT_AVAILABLE:
        return None
    client = get_hubspot_client()
    if not client or not prospect_note.prospect.hubspot_id:
        return None

    properties = {
        "hs_note_body": prospect_note.content,
        "hs_timestamp": int(prospect_note.created_at.timestamp() * 1000)
    }

    try:
        # Create the note object
        note_res = client.crm.objects.notes.basic_api.create(
            simple_public_object_input=NoteInput(properties=properties)
        )
        note_id = note_res.id

        # Associate note with contact
        client.crm.associations.v4.basic_api.create(
            object_type="notes",
            object_id=note_id,
            to_object_type="contacts",
            to_object_id=prospect_note.prospect.hubspot_id,
            association_spec=[
                {
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": 202 # Note to Contact
                }
            ]
        )

        prospect_note.hubspot_note_id = note_id
        prospect_note.save(update_fields=['hubspot_note_id'])
        return note_id

    except ApiException as e:
        logger.error(f"HubSpot API error sync_note: {e}")
        return None
