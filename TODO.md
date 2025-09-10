# TODO: Fix Container Type Switching

## Steps to Complete:
- [x] Add new view `get_container_sizes` in `optimization/views.py` to return JSON of container sizes for given container_type
- [x] Add URL pattern for `get_container_sizes` in `optimization/urls.py`
- [x] Update JavaScript in `optimization/templates/optimization/upload.html` to AJAX fetch sizes on container_type change
- [x] Test the dynamic filtering functionality
- [x] Verify form submission works with selected sizes
    