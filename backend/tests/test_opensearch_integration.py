from opensearchpy import OpenSearch
import pytest


@pytest.mark.opensearch
def test_search_with_ephemeral(os_ephemeral_index):
    client = OpenSearch([{"host": "localhost", "port": 9200}], http_compress=True, verify_certs=False)
    index_name = os_ephemeral_index

    docs = [
        {"id": "1", "title": "Product Handbook", "text": "The product handbook explains grounded answers."},
        {"id": "2", "title": "Support Policy", "text": "The support policy defines priority levels."},
    ]
    for doc in docs:
        client.index(index=index_name, id=doc["id"], body=doc)
    client.indices.refresh(index=index_name)

    res = client.search(index=index_name, body={
        "query": {"multi_match": {"query": "product handbook", "fields": ["title^2", "text"], "operator": "and"}}
    })
    assert res["hits"]["hits"]
