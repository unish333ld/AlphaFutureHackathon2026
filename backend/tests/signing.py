"""Tests use the same explicit document/attempt protocol as browser clients."""

from agreements import services
from agreements.demo_codes import DemoCodeAdapter
from agreements.documents import generate_document
from agreements.models import Agreement


def signing_payload(user, agreement, version):
    if not isinstance(agreement, Agreement):
        agreement = Agreement.objects.get(pk=agreement["id"])
    document = generate_document(
        user, agreement.pk, version=version, document_hash=agreement.document_hash
    )
    attempt = services.start_signature_attempt(
        user, agreement.pk, version, agreement.document_hash, document.pk, document.pdf_sha256
    )
    return {
        "lock_version": version,
        "document_hash": agreement.document_hash,
        "confirm_simulation": True,
        "document_id": str(document.pk),
        "pdf_sha256": document.pdf_sha256,
        "attempt_id": str(attempt.pk),
        "code": DemoCodeAdapter.code(attempt.pk),
    }


def sign_with_code(user, agreement_id, version, document_hash):
    agreement = Agreement.objects.get(pk=agreement_id)
    data = signing_payload(user, agreement, version)
    return services.sign_agreement(
        user,
        agreement_id,
        version,
        document_hash,
        **{key: data[key] for key in ("attempt_id", "document_id", "pdf_sha256", "code")},
    )
