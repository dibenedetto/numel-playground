# tools

def square_tool(n: int) -> int:
	"""
	Return the square of a number.
	Args:
		n (int): The number to be squared.
	Returns:
		int: The square of the number.
	Examples:
		>>> square_tool(3)
		9
		>>> square_tool(-4)
		16
		>>> square_tool(0)
		0
	"""
	result = n**2
	return result
