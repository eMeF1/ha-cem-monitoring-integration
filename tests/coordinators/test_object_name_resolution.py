"""Tests for object name resolution with parent hierarchy."""

# conftest.py handles path setup and Home Assistant mocking
from custom_components.cem_monitor.config_flow import _resolve_object_name


class TestObjectNameResolution:
    """Test _resolve_object_name function with various scenarios."""

    def test_direct_name_resolution(self):
        """Test that object with name directly returns the name."""
        mis_id = 1
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Object 1"},
        }
        mis_name_by_id = {
            1: "Object 1",
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        assert name == "Object 1"
        assert source_id == 1

    def test_parent_climbing_single_level(self):
        """Test that object without name climbs to parent with name."""
        mis_id = 2
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Parent Object"},
            2: {"mis_id": 2, "mis_idp": 1},  # No name, has parent
        }
        mis_name_by_id = {
            1: "Parent Object",
            2: None,  # No name
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        assert name == "Parent Object"
        assert source_id == 1  # Source is parent

    def test_parent_climbing_multi_level(self):
        """Test climbing through multiple parent levels."""
        mis_id = 3
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Root Object"},
            2: {"mis_id": 2, "mis_idp": 1},  # No name, parent is 1
            3: {"mis_id": 3, "mis_idp": 2},  # No name, parent is 2
        }
        mis_name_by_id = {
            1: "Root Object",
            2: None,  # No name
            3: None,  # No name
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        assert name == "Root Object"
        assert source_id == 1  # Source is root

    def test_circular_reference_detection(self):
        """Test that circular references are detected and prevented."""
        mis_id = 1
        raw_by_mis = {
            1: {"mis_id": 1, "mis_idp": 2},  # Points to 2
            2: {"mis_id": 2, "mis_idp": 1},  # Points to 1 (circular)
        }
        mis_name_by_id = {
            1: None,  # No name
            2: None,  # No name
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should return None, None because of circular reference
        assert name is None
        assert source_id is None

    def test_missing_parent_handling(self):
        """Test handling when parent is None or missing."""
        mis_id = 1
        raw_by_mis = {
            1: {"mis_id": 1, "mis_idp": None},  # Parent is None
        }
        mis_name_by_id = {
            1: None,  # No name
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should return None, None because no name and no valid parent
        assert name is None
        assert source_id is None

    def test_missing_parent_in_raw(self):
        """Test handling when parent key is missing from raw data."""
        mis_id = 1
        raw_by_mis = {
            1: {"mis_id": 1},  # No mis_idp key
        }
        mis_name_by_id = {
            1: None,  # No name
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should return None, None because no name and no parent
        assert name is None
        assert source_id is None

    def test_none_mis_id(self):
        """Test handling when mis_id is None."""
        mis_id = None
        raw_by_mis = {}
        mis_name_by_id = {}

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should return None, None immediately
        assert name is None
        assert source_id is None

    def test_parent_not_in_raw_by_mis(self):
        """Test handling when parent ID exists but not in raw_by_mis."""
        mis_id = 2
        raw_by_mis = {
            2: {"mis_id": 2, "mis_idp": 999},  # Parent 999 doesn't exist
        }
        mis_name_by_id = {
            2: None,  # No name
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should return None, None because parent doesn't exist
        assert name is None
        assert source_id is None

    def test_name_field_variations(self):
        """Test name resolution with various name field names."""
        # Test mis_nazev
        mis_id = 1
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Name 1"},
        }
        mis_name_by_id = {
            1: "Name 1",
        }
        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)
        assert name == "Name 1"
        assert source_id == 1

        # Test mis_name
        raw_by_mis = {
            2: {"mis_id": 2, "mis_name": "Name 2"},
        }
        mis_name_by_id = {
            2: "Name 2",
        }
        name, source_id = _resolve_object_name(2, raw_by_mis, mis_name_by_id)
        assert name == "Name 2"
        assert source_id == 2

        # Test name
        raw_by_mis = {
            3: {"mis_id": 3, "name": "Name 3"},
        }
        mis_name_by_id = {
            3: "Name 3",
        }
        name, source_id = _resolve_object_name(3, raw_by_mis, mis_name_by_id)
        assert name == "Name 3"
        assert source_id == 3

    def test_empty_string_name_handling(self):
        """Test that empty string names are treated as None."""
        mis_id = 2
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Parent Object"},
            2: {"mis_id": 2, "mis_idp": 1},
        }
        mis_name_by_id = {
            1: "Parent Object",
            2: "",  # Empty string should be treated as None
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should climb to parent because empty string is not valid
        assert name == "Parent Object"
        assert source_id == 1

    def test_whitespace_only_name_handling(self):
        """Test that whitespace-only names are treated as None."""
        mis_id = 2
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Parent Object"},
            2: {"mis_id": 2, "mis_idp": 1},
        }
        mis_name_by_id = {
            1: "Parent Object",
            2: "   ",  # Whitespace only should be treated as None
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should climb to parent because whitespace-only is not valid
        assert name == "Parent Object"
        assert source_id == 1

    def test_invalid_parent_id_type(self):
        """Test handling when parent ID is not a valid integer."""
        mis_id = 2
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Parent Object"},
            2: {"mis_id": 2, "mis_idp": "not_an_int"},  # Invalid parent ID type
        }
        mis_name_by_id = {
            1: "Parent Object",
            2: None,
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should return None, None because parent ID is invalid
        assert name is None
        assert source_id is None

    def test_complex_hierarchy(self):
        """Test complex hierarchy with multiple levels and named/unnamed objects."""
        mis_id = 5
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Root"},
            2: {"mis_id": 2, "mis_idp": 1},  # No name
            3: {"mis_id": 3, "mis_nazev": "Branch", "mis_idp": 1},
            4: {"mis_id": 4, "mis_idp": 3},  # No name
            5: {"mis_id": 5, "mis_idp": 4},  # No name, should climb to 3
        }
        mis_name_by_id = {
            1: "Root",
            2: None,
            3: "Branch",
            4: None,
            5: None,
        }

        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)

        # Should find "Branch" at level 3
        assert name == "Branch"
        assert source_id == 3

    def test_parent_with_different_field_names(self):
        """Test parent resolution with different parent field name variations."""
        mis_id = 2
        # Test with mis_idp
        raw_by_mis = {
            1: {"mis_id": 1, "mis_nazev": "Parent 1"},
            2: {"mis_id": 2, "mis_idp": 1},
        }
        mis_name_by_id = {
            1: "Parent 1",
            2: None,
        }
        name, source_id = _resolve_object_name(mis_id, raw_by_mis, mis_name_by_id)
        assert name == "Parent 1"
        assert source_id == 1
