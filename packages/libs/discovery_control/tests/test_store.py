from discovery_control.store import ControlStore


class FakeResource:
    def __init__(self, table):
        self._table = table

    def Table(self, table_name):
        return self._table


class FakePaginatedTable:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        if "ExclusiveStartKey" in kwargs:
            page_index = kwargs["ExclusiveStartKey"]["page"]
        else:
            page_index = 0
        return self.pages[page_index]


def test_list_spots_paginates_and_filters_terminal_status():
    table = FakePaginatedTable(
        [
            {
                "Items": [
                    {"spot_id": "b", "terminal_status": "success"},
                    {"spot_id": "failed", "terminal_status": "failed"},
                ],
                "LastEvaluatedKey": {"page": 1},
            },
            {
                "Items": [{"spot_id": "a", "terminal_status": "success"}],
            },
        ]
    )
    store = ControlStore(table_name="table", dynamodb_resource=FakeResource(table))

    spots = store.list_spots("run-1", terminal_status="success")

    assert [spot["spot_id"] for spot in spots] == ["a", "b"]
    assert len(table.calls) == 2
    assert "ExclusiveStartKey" not in table.calls[0]
    assert table.calls[1]["ExclusiveStartKey"] == {"page": 1}
