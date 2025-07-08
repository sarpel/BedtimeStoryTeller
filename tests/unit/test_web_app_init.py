import pytest
import os
import sys

# Add the project root to the Python path to allow for correct module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

def test_web_app_initialization_avoids_jinja2_error():
    """
    Tests that the WebApplication can be initialized without assertion errors.
    This test specifically targets the 'jinja2 must be installed' error to prevent regression.
    """
    try:
        # The WebApplication is instantiated at the module level in app.py,
        # so simply importing it will trigger the constructor and the error.
        from storyteller.web.app import WebApplication
        
        # If the import succeeds and the web_app object is created, the test passes.
        # We can perform a basic check on the created instance.
        assert WebApplication() is not None

    except AssertionError as e:
        # Fail the test if the specific Jinja2 assertion error is raised.
        if "jinja2 must be installed" in str(e):
            pytest.fail(f"Caught the specific Jinja2 initialization error: {e}")
        else:
            # Fail for any other assertion errors too.
            pytest.fail(f"An unexpected AssertionError occurred during WebApplication initialization: {e}")
    except ImportError as e:
        pytest.fail(f"Failed to import necessary modules for the test: {e}")

