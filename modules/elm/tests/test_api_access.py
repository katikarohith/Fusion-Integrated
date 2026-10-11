from rest_framework.test import APIClient

from conftest import make_session


def _client(stub_iam, *, modules, permissions):
    stub_iam(make_session(user_id=71, kind="staff", modules=modules, permissions=permissions))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token test")
    return client


def test_permission_without_module_grant_cannot_read_elm_types(stub_iam):
    client = _client(stub_iam, modules=(), permissions=("leave_elm.application.view",))
    response = client.get("/api/v1/elm/types")
    assert response.status_code == 403


def test_module_grant_without_action_permission_cannot_read_elm_types(stub_iam):
    client = _client(stub_iam, modules=("leave_elm",), permissions=())
    response = client.get("/api/v1/elm/types")
    assert response.status_code == 403
