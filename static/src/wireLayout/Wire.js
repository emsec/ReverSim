/**
 * 
 */
class Wire
{
	constructor(element)
	{
		this.points = new Array();
		this.origin = element;
	}

	/**
	 * Add a vertex to this wire.
	 * @param {Point} point The 2d coordinate of the new point.
	 */
	addPoint(point)
	{
		this.points.push([point.x, point.y]);
	}

	/**
	 * 
	 * @returns An array of 2d arrays containing the points.
	 */
	getPoints()
	{
		return this.points;
	}

	/**
	 * Calculate the entire length of this wire.
	 * @returns The accumulated Manhattan distance of all points.
	 */
	getLength()
	{
		let sum = 0;
		let lastPoint = this.points[0];
		for(const point of this.points)
		{
			if(lastPoint == point) // Skip the first point, as length would be zero
				continue;
			
			const a = 
			sum += Wire.manhattanDistance(point, lastPoint);
			lastPoint = point;
		}

		return sum;
	}
}

/**
 * Calculate the Manhattan-/Minkowski-/Cityblock distance between points `a` and `b`.
 * @param {number[]} a A 2d Array containing the first coordinate.
 * @param {number[]} b A 2d array containing the second coordinate.
 */
Wire.manhattanDistance = function(a, b)
{
	console.assert(a.length == 2, `The coordinate for a should be 2D, got ${a.length}`);
	console.assert(b.length == 2, `The coordinate for b should be 2D, got ${a.length}`);
	return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);
}
