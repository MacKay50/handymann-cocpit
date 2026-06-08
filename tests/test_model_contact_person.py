"""Assert ContactPerson model fields and defaults."""
from haandvaerker.models.contact_person import ContactPerson, ContactPersonRead


def test_contact_person_fields() -> None:
    fields = ContactPerson.model_fields
    for f in (
        "id",
        "company_id",
        "name",
        "phone",
        "email",
        "title",
        "contact_type",
        "customer_id",
        "project_id",
        "tags",
        "comment",
        "active",
    ):
        assert f in fields, f"Expected field '{f}' missing from ContactPerson"


def test_contact_person_defaults() -> None:
    fields = ContactPersonRead.model_fields
    assert fields["contact_type"].default == "other"
    assert fields["active"].default is True
