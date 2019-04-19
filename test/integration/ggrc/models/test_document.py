# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for Document"""
import json
from mock import mock

from werkzeug.exceptions import Unauthorized

from ggrc.gdrive import GdriveUnauthorized
from ggrc.models import all_models
from ggrc.models import exceptions
from integration.ggrc import TestCase
from integration.ggrc.api_helper import Api
from integration.ggrc import generator
from integration.ggrc.models import factories


# pylint: disable=unused-argument
def dummy_gdrive_response_link(*args, **kwargs):
  return 'http://mega.doc'


class TestDocument(TestCase):
  """Document test cases"""
  # pylint: disable=invalid-name
  # pylint: disable=no-self-use
  # pylint: disable=too-many-public-methods

  def setUp(self):
    super(TestDocument, self).setUp()
    self.api = Api()
    self.gen = generator.ObjectGenerator()

  def test_get_parent_obj_control_type(self):
    """Test mapping parent of Control type"""
    control = factories.ControlFactory()
    document = factories.DocumentFileFactory(
        parent_obj={
            'id': control.id,
            'type': 'Control'
        })
    expected_control = document.related_objects(_types=[control.type]).pop()
    self.assertEqual(expected_control, control)

  def test_parent_obj_validation_is_id_presents(self):
    """Validation parent_obj id should present."""
    with self.assertRaises(exceptions.ValidationError):
      factories.DocumentFileFactory(
          parent_obj={
              'type': 'Control'
          })

  def test_parent_obj_validation_is_type_presents(self):
    """Validation parent_obj type should present."""
    control = factories.ControlFactory()
    with self.assertRaises(exceptions.ValidationError):
      factories.DocumentFileFactory(
          parent_obj={
              'id': control.id
          })

  def test_parent_obj_validation_wrong_type(self):
    """Validation parent_obj type.

    Type should be Documentable.
    """
    audit = factories.AuditFactory()
    with self.assertRaises(exceptions.ValidationError):
      factories.DocumentFileFactory(
          parent_obj={
              'id': audit.id,
              'type': 'Audit'
          })

  def test_update_title(self):
    """Test update document title."""
    create_title = "test_title"
    update_title = "update_test_title"
    document = factories.DocumentFactory(title=create_title)
    response = self.api.put(document, {"title": update_title})
    self.assert200(response)
    self.assertEqual(all_models.Document.query.get(document.id).title,
                     update_title)

  def create_document_by_type(self, kind):
    """Create document with sent type."""
    data = {
        "title": "test_title",
        "link": "test_link",
    }
    if kind is not None:
      data["kind"] = kind
    kind = kind or all_models.Document.REFERENCE_URL
    resp, doc = self.gen.generate_object(
        all_models.Document,
        data
    )
    self.assertTrue(
        all_models.Document.query.filter(
            all_models.Document.id == resp.json["document"]["id"],
            all_models.Document.kind == kind,
        ).all()
    )
    return (resp, doc)

  def test_create_reference_url(self):
    """Test create reference url."""
    self.create_document_by_type(all_models.Document.REFERENCE_URL)

  def test_create_reference_url_default(self):
    """Test create reference url(default)."""
    self.create_document_by_type(None)

  def test_create_evidence(self):
    """Test create evidence."""
    self.create_document_by_type(all_models.Document.FILE)

  def test_create_invalid_type(self):
    """Test validation kind."""
    data = {
        "kind": 3,
        "title": "test_title",
        "link": "test_link",
        "owners": [self.gen.create_stub(all_models.Person.query.first())],
    }
    obj_name = all_models.Document._inflector.table_singular
    obj = all_models.Document()
    obj_dict = self.gen.obj_to_dict(obj, obj_name)
    obj_dict[obj_name].update(data)
    resp = self.api.post(all_models.Document, obj_dict)
    self.assert400(resp)
    self.assertEqual('"Invalid value for attribute kind. '
                     'Expected options are `FILE`, '
                     '`REFERENCE_URL`"',
                     resp.data)

  def test_header_on_expected_error(self):
    """During authorization flow we have the expected 'Unauthorized'.

    To allow FE ignore the error popup we need to set
    'X-Expected-Error' header
    """
    control = factories.ControlFactory()
    response = self.api.post(all_models.Document, [{
        "document": {
            "kind": all_models.Document.FILE,
            "source_gdrive_id": "some link",
            "link": "some link",
            "title": "some title",
            "context": None,
            "parent_obj": {
                "id": control.id,
                "type": "Control"
            }
        }
    }])
    self.assertEqual(response.status_code, 401)
    self.assertIn('X-Expected-Error', response.headers)

  def test_header_on_unexpected_error(self):
    """During authorization flow we have the expected 'Unauthorized'.

    If error is unexpected we need to make sure that 'X-Expected-Error'
    header is not set.
    """
    # pylint: disable=unused-argument
    def side_effect_function(*args, **kwargs):
      raise Unauthorized("Unable to get valid credentials")

    with mock.patch("ggrc.gdrive.file_actions.get_gdrive_file_link") as mocked:
      mocked.side_effect = side_effect_function
      control = factories.ControlFactory()
      response = self.api.post(all_models.Document, [{
          "document": {
              "kind": all_models.Document.FILE,
              "source_gdrive_id": "some link",
              "link": "some link",
              "title": "some title",
              "context": None,
              "parent_obj": {
                  "id": control.id,
                  "type": "Control"
              }
          }
      }])
    self.assertEqual(response.status_code, 401)
    self.assertNotIn('X-Expected-Error', response.headers)

  def test_header_on_expected_error_batch(self):
    """During authorization flow we have the expected 'Unauthorized'.

    To allow FE ignore popup we need to set 'X-Expected-Error' header
    """
    # pylint: disable=unused-argument
    def side_effect_function(*args, **kwargs):
      raise GdriveUnauthorized("Unable to get valid credentials")

    with mock.patch("ggrc.gdrive.file_actions.get_gdrive_file_link") as mocked:
      mocked.side_effect = side_effect_function
      control = factories.ControlFactory()

      doc1 = {
          "document": {
              "kind": all_models.Document.FILE,
              "source_gdrive_id": "some link",
              "link": "some link",
              "title": "some title",
              "context": None,
              "parent_obj": {
                  "id": control.id,
                  "type": "Control"
              }
          }
      }
      doc2 = {
          "document": {
              "kind": all_models.Document.REFERENCE_URL,
              "link": "some link",
              "title": "some title",
              "context": None,
          }
      }

    response = self.api.post(all_models.Document, [doc1, doc2])
    self.assertEqual(response.status_code, 401)
    self.assertIn('X-Expected-Error', response.headers)

  def test_create_document_by_api(self,
                                  kind=all_models.Document.REFERENCE_URL):
    """Test crete document via POST"""
    document_data = dict(
        title='Simple title',
        kind=kind,
        link='some_url.com',
        description='mega description'
    )
    _, document = self.gen.generate_object(
        all_models.Document,
        document_data
    )

    result = all_models.Document.query.filter(
        all_models.Document.id == document.id).one()

    self.assertEqual(result.title, 'Simple title')
    self.assertEqual(result.kind, kind)
    self.assertEqual(result.link, 'some_url.com')
    self.assertEqual(result.description, 'mega description')

  @mock.patch('ggrc.gdrive.file_actions.get_gdrive_file_link',
              dummy_gdrive_response_link)
  def test_create_document_file_by_api(self, kind=all_models.Document.FILE):
    """Test crete document.FILE via POST"""
    document_data = dict(
        title='Simple title',
        kind=kind,
        source_gdrive_id='1234',
        description='mega description'
    )
    _, document = self.gen.generate_object(
        all_models.Document,
        document_data
    )

    result = all_models.Document.query.filter(
        all_models.Document.id == document.id).one()

    self.assertEqual(result.slug, 'DOCUMENT-{}'.format(result.id))
    self.assertEqual(result.title, 'Simple title')
    self.assertEqual(result.kind, kind)
    self.assertEqual(result.link, 'http://mega.doc')
    self.assertEqual(result.description, 'mega description')
    self.assertEqual(result.status, all_models.Document.START_STATE)

  def test_document_ref_url_type_with_parent(self):
    """Document of REFERENCE_URL type mapped to parent if parent specified"""
    control = factories.ControlFactory()
    document = factories.DocumentReferenceUrlFactory(
        description='mega description',
        parent_obj={
            'id': control.id,
            'type': 'Control'
        }
    )
    rel_evidences = control.related_objects(_types=[document.type])
    self.assertEqual(document, rel_evidences.pop())

  def test_document_url_for_ariane_with_parent(self):
    """Document of URL_FOR_ARIANE type mapped to parent if parent specified"""
    system = factories.SystemFactory()
    document = factories.DocumentURLForArianeFactory(
        description='mega description',
        parent_obj={
            'id': system.id,
            'type': 'System',
        }
    )
    rel_urls_for_ariane = system.related_objects(_types=[document.type])
    self.assertEqual(document, rel_urls_for_ariane.pop())

  def test_document_url_for_spur_with_parent(self):
    """Document of URL_FOR_SPUR type mapped to parent if parent specified"""
    system = factories.SystemFactory()
    document = factories.DocumentURLForSPURFactory(
        description='mega description',
        parent_obj={
            'id': system.id,
            'type': 'System',
        }
    )
    rel_urls_for_spur = system.related_objects(_types=[document.type])
    self.assertEqual(document, rel_urls_for_spur.pop())

  def test_document_make_admin_endpoint(self):
    """Test /api/document/make_admin endpoint

    should add current user as document admin
    """

    _, editor = self.gen.generate_person(
        user_role="Creator"
    )

    doc = factories.DocumentFileFactory(gdrive_id="123")
    doc_id = doc.id
    self.api.set_user(editor)
    request_data = json.dumps(dict(gdrive_ids=["123", "456"]))
    response = self.api.client.post("/api/document/make_admin",
                                    data=request_data,
                                    content_type="application/json")

    updated = [obj for obj in response.json if obj["updated"]]
    not_updated = [obj for obj in response.json if not obj["updated"]]

    self.assertEquals(len(updated), 1)
    self.assertEquals(updated[0]["object"]["id"], doc_id)
    self.assertEquals(len(not_updated), 1)

    doc = all_models.Document.query.filter_by(id=doc_id).one()
    self.assertEquals(len(doc.access_control_list), 1)
    control_user = all_models.Person.query.get(editor.id)
    self.assertIn(control_user.id,
                  [person.id for person, acr in doc.access_control_list])

  def test_api_documents_exist(self):
    """Test /api/document/documents_exist"""
    with factories.single_commit():
      doc1 = factories.DocumentFileFactory(gdrive_id="123")
      doc1_id = doc1.id
      factories.DocumentFileFactory(gdrive_id="456")
    endpoint_uri = "/api/document/documents_exist"
    request_data1 = json.dumps(dict(gdrive_ids=["123", "456"]))
    response1 = self.api.client.post(endpoint_uri, data=request_data1,
                                     content_type="application/json")

    self.assertEquals(len(response1.json), 2)
    self.assertTrue(all([r["exists"] for r in response1.json]))

    request_data2 = json.dumps(dict(gdrive_ids=["123", "999"]))
    response2 = self.api.client.post(endpoint_uri, data=request_data2,
                                     content_type="application/json")
    self.assertEquals(len(response2.json), 2)
    existing = [obj for obj in response2.json if obj["exists"]]
    not_existing = [obj for obj in response2.json if not obj["exists"]]
    self.assertEquals(len(existing), 1)
    self.assertEquals(len(not_existing), 1)
    self.assertEquals(existing[0]["object"]["id"], doc1_id)

  def test_add_to_parent_folder(self):
    """If parent has folder => add document to that folder"""
    method_to_patch = 'ggrc.gdrive.file_actions.add_gdrive_file_folder'
    with mock.patch(method_to_patch) as mocked:
      mocked.return_value = 'http://mega.doc'
      with factories.single_commit():
        control = factories.ControlFactory(folder="gdrive_folder_id")
        factories.DocumentFileFactory(
            source_gdrive_id="source_gdrive_id",
            parent_obj={
                "id": control.id,
                "type": "Control"
            }
        )
    mocked.assert_called_with("source_gdrive_id", "gdrive_folder_id")

  def test_add_to_parent_folder_relationship(self):
    """If parent has folder => add document to that folder mapped via rel"""
    method_to_patch = 'ggrc.gdrive.file_actions.add_gdrive_file_folder'
    with mock.patch(method_to_patch) as mocked:
      mocked.return_value = 'http://mega.doc'
      with factories.single_commit():
        control = factories.ControlFactory(folder="gdrive_folder_id")
        control_id = control.id
        doc = factories.DocumentFileFactory(
            source_gdrive_id="source_gdrive_id",
            link='some link'
        )
        doc_id = doc.id

      response = self.api.post(all_models.Relationship, {
          "relationship": {
              "source": {"id": control_id, "type": control.type},
              "destination": {"id": doc_id, "type": doc.type},
              "context": None
          },
      })

    self.assertStatus(response, 201)
    mocked.assert_called_with("source_gdrive_id", "gdrive_folder_id")

  def test_add_to_parent_folder_not_specified(self):
    """If parent has not folder => just save gdrive link"""
    with mock.patch('ggrc.gdrive.file_actions.get_gdrive_file_link') as mocked:
      mocked.return_value = 'http://mega.doc'
      with factories.single_commit():
        control = factories.ControlFactory()
        factories.DocumentFileFactory(
            source_gdrive_id="source_gdrive_id",
            parent_obj={
                "id": control.id,
                "type": "Control"
            }
        )
    mocked.assert_called_with("source_gdrive_id")
