# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime

import elasticsearch1_dsl
import pytest

import h.search.index
from tests.common.matchers import Matcher


@pytest.mark.usefixtures("annotations")
class TestIndex(object):
    def test_annotation_ids_are_used_as_elasticsearch_ids(self, es_client,
                                                          make_annotation,
                                                          index):
        annotation = make_annotation()

        index(annotation)

        result = es_client.conn.get(index=es_client.index,
                                    doc_type="annotation",
                                    id=annotation.id)
        assert result["_id"] == annotation.id

    def test_it_can_index_an_annotation_with_no_document(self, factories,
                                                         make_annotation,
                                                         index, get):
        annotation = make_annotation(document=None)

        index(annotation)

        assert get(annotation.id)["document"] == {}

    def test_it_indexes_the_annotations_document_web_uri(self, factories,
                                                         make_annotation,
                                                         index, get):
        annotation = make_annotation(
            document=factories.Document.build(web_uri="https://example.com/example_article"),
        )

        index(annotation)

        # *Searching* for an annotation by ``annotation.document`` (e.g. by
        # document ``title`` or ``web_uri``) isn't enabled.  But you can
        # retrieve an annotation by ID, or by searching on other field(s), and
        # then access its ``document``. Bouncer
        # (https://github.com/hypothesis/bouncer) accesses h's Elasticsearch
        # index directly and uses this ``document`` field.
        assert get(annotation.id)["document"]["web_uri"] == "https://example.com/example_article"

    def test_it_can_index_an_annotation_with_a_document_with_no_web_uri(self, make_annotation,
                                                                        factories, index, get):
        annotation = make_annotation(
            document=factories.Document.build(web_uri=None),
        )

        index(annotation)

        assert "web_uri" not in get(annotation.id)["document"]

    def test_it_indexes_the_annotations_document_title(self, factories,
                                                       make_annotation,
                                                       index, get):
        annotation = make_annotation(
            document=factories.Document.build(title="test_document_title"),
        )

        index(annotation)

        assert get(annotation.id)["document"]["title"] == ["test_document_title"]

    def test_it_can_index_an_annotation_with_a_document_with_no_title(self, factories,
                                                                      make_annotation,
                                                                      index, get):
        annotation = make_annotation(
            document=factories.Document.build(title=None),
        )

        index(annotation)

        assert "title" not in get(annotation.id)["document"]

    def test_you_can_filter_annotations_by_authority(self, make_annotation, index, search):
        annotation = make_annotation(userid="acct:someone@example.com")

        index(annotation)

        response = search.filter("term", authority="example.com").execute()
        assert SearchResponseWithIDs([annotation.id]) == response

    def test_you_can_filter_annotations_by_creation_time(self, factories, index, search):
        before = datetime.datetime.now()
        annotation = factories.Annotation.build(id="test_annotation_id", created=datetime.datetime.now())

        index(annotation)

        response = search.filter("range", created={"gte": before}).execute()
        assert SearchResponseWithIDs([annotation.id]) == response

    @pytest.fixture
    def make_annotation(self, factories):
        """A helper function for making test annotations."""
        def _make_annotation(id_=None, **kwargs):
            now = datetime.datetime.now()
            # We call .build() so that the annotation doesn't get added to the
            # DB (so the tests run faster) but then we have to pass in our own
            # id, created, updated etc because our tests need these and they
            # wouldn't normally be created until the annotation actually gets
            # added to the DB.
            return factories.Annotation.build(
                id=id_ or "test_annotation_id",
                created=now,
                updated=now,
                **kwargs)
        return _make_annotation

    @pytest.fixture
    def annotations(self, factories, index):
        """
        Add some annotations to Elasticsearch as "noise".

        These are annotations that we *don't* expect to show up in search
        results. We want some noise in the search index to make sure that the
        test search queries are only returning the expected annotations and
        not, for example, simply returning *all* annotations.

        """
        index(
            factories.Annotation.build(id="noise_annotation_1"),
            factories.Annotation.build(id="noise_annotation_2"),
            factories.Annotation.build(id="noise_annotation_3"),
        )

    @pytest.fixture
    def get(self, es_client):
        def _get(annotation_id):
            """Return the annotation with the given ID from Elasticsearch."""
            return es_client.conn.get(
                index=es_client.index, doc_type="annotation",
                id=annotation_id)["_source"]
        return _get

    @pytest.fixture
    def index(self, es_client, pyramid_request):
        def _index(*annotations):
            """Index the given annotation(s) into Elasticsearch."""
            for annotation in annotations:
                h.search.index.index(es_client, annotation, pyramid_request)
            es_client.conn.indices.refresh(index=es_client.index)
        return _index

    @pytest.fixture
    def search(self, es_client):
        return elasticsearch1_dsl.Search(using=es_client.conn).fields([])


class SearchResponseWithIDs(Matcher):
    """
    Matches an elasticsearch1_dsl response with the given annotation ids.

    Matches any :py:class:`elasticsearch1_dsl.result.Response` search
    response object whose search results are exactly the annotations with
    the given ids, in the given order.

    """
    def __init__(self, annotation_ids):
        self.annotation_ids = annotation_ids

    def __eq__(self, search_response):
        ids = [search_result.meta["id"] for search_result in search_response]
        return ids == self.annotation_ids
