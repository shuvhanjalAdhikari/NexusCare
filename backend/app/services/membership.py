# ================================================================
# NexusCare — app/services/membership.py
# Hospital membership management: adding, suspending, revoking members.
# ================================================================

# ----------------------------------------------------------------
# INVITE-BY-EMAIL — HARD RULE (implement in user-management phase)
# ----------------------------------------------------------------
#
# When adding a user to a hospital, always check whether the email
# already exists in the users table:
#
#   - Email EXISTS → create only a new HospitalMembership row pointing
#     at the existing User. Never create a second User record.
#
#   - Email NOT found → create the User record first, then create the
#     HospitalMembership. Send a set-password invitation email.
#
# This invariant keeps user accounts globally unique and prevents the
# same person from having two separate identities in the platform.
# Violating it will break login (global email lookup would return
# an arbitrary one of the duplicates).
