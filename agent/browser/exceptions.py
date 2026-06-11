class ElementNotFoundError(Exception):
    """Raised when an action references an element_id that perception did not return."""

    def __init__(self, element_id: int):
        super().__init__(f"No element with id {element_id} in the current page state")
        self.element_id = element_id
