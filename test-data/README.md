# Test label images for OCR and pipeline evaluation.
#
# Place sample images in the condition folders below. Do not commit proprietary
# or personally identifying materials without clearance.
#
# Folders:
#   clean/           — well-lit, frontal labels (baseline)
#   angled/          — perspective / rotation stress
#   glare/           — reflection / lighting stress
#   warning-errors/  — government warning issues (for later rule tests)
#   mismatches/      — application vs label disagreements
#
# Phase 2 note: preprocessing/validation unit tests primarily use programmatic
# fixtures in backend/tests/image_fixtures.py. Real label photos belong here for
# OCR evaluation in a later phase.
