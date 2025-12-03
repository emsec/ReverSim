/**
 * Draw the wires of the circuit
 */
class LineDrawer extends Phaser.GameObjects.GameObject
{
	/**
	 * 
	 * @param {Phaser.Scene} scene The parent `Phaser.Scene`.
	 * @param {Wire[]} wires The list of wires to draw in Manhattan/Cityblock style.
	 * @param {boolean} showState Display if the wire conducts current (logical 1) or is off (logical 0).
	 */
	constructor(scene, wires, showState)
	{
		super(scene, 'line_drawer');
		scene.add.existing(this);

		// constructor values
		this.scene = scene;
		this.wires = wires;
		this.showState = showState;

		this.graphicLine = this.scene.add.graphics();
		this.graphicLine.setDepth(5);

		this.lineWidth = 2;

		// Properties
		this.getHorizontalLines();
	}


	getHorizontalLines()
	{
		this.horizontalLines = {};

		for(const wire of this.wires)
		{
			// copy points 
			var points = [];
			for(var p of wire.getPoints())
				points.push([p[0], p[1]]);

			var firstPoint = points.shift();

			for(const secondPoint of points)
			{
				// test if line is a horizontal line
				// = check if y-coordinate is equal 
				var y1 = firstPoint[1];
				var y2 = secondPoint[1];
				if(y1 == y2)
				{
					// add horizontal connection to list
					if(!(y1 in this.horizontalLines))
						this.horizontalLines[y1] = []

					var x1 = firstPoint[0];
					var x2 = secondPoint[0];
					this.horizontalLines[y1].push([x1, x2]);
				}

				firstPoint = [secondPoint[0], secondPoint[1]];
			}
		}
		return this.horizontalLines;
	}


	setScale(scaleFactor)
	{
		this.lineWidth = this.lineWidth * scaleFactor;
		this.drawWires();
	}


	checkInterceptions(firstPoint, secondPoint, graphicLine)
	{
		var interceptions = new Set();
		var radius = 15;

		// check if this is a vertical line
		if(firstPoint[0] == secondPoint[0])
		{
			var y1 = firstPoint[1];
			var y2 = secondPoint[1];

			// check if horizontal lines exist between those two lines
			for(var key in this.horizontalLines)
			{
				var yCoord = parseInt(key);

				if(yCoord > y1 && yCoord < y2 || yCoord > y2 && yCoord < y1)
				{

					// check if x-coordinate of horizontal line matches a horizontal line
					var x = firstPoint[0]
					for(var connection of this.horizontalLines[key])
					{
						var x1 = connection[0];
						var x2 = connection[1];

						var x = firstPoint[0];

						if(x > x1 && x < x2 || x > x2 && x < x1)
						{
							// there is an intersection point
							// interceptions.push( [x, yCoord] );

							// store interceptions
							if(!interceptions.has(yCoord))
							{
								interceptions.add(yCoord);
							}

							let a = this.scene.levelToScreenCoords(x, yCoord);

							// x, y, xRadius, yRadius, startAngle, endAngle, clockwise, rotation
							var curve = new Phaser.Curves.Ellipse(a.x, a.y, radius / 2, radius, -90, 90, false);
							curve.draw(graphicLine, 64);
						}
					}
				}
			}
		}

		// return interceptions;

		var intermediatePoint = [firstPoint[0], firstPoint[1]];

		let interceptionArray = Array.from(interceptions);
		interceptionArray.sort();

		if(interceptionArray.length == 0)
		{
			let a = this.scene.levelToScreenCoords(intermediatePoint[0], intermediatePoint[1]);
			let b = this.scene.levelToScreenCoords(secondPoint[0], secondPoint[1]);
			graphicLine.moveTo(a.x, a.y);
			graphicLine.lineTo(b.x, b.y);
			graphicLine.strokePath();

			return;
		}

		if(intermediatePoint[1] > secondPoint[1]) 
			interceptionArray.reverse();

		let interceptX = firstPoint[0];
		for(let interceptY of interceptionArray)
		{

			// draw lines 
			let a = this.scene.levelToScreenCoords(interceptX, intermediatePoint[1]);
			graphicLine.moveTo(a.x, a.y);

			if(intermediatePoint[1] < secondPoint[1])
			{
				let b = this.scene.levelToScreenCoords(interceptX, interceptY - radius);
				graphicLine.lineTo(b.x, b.y);
				graphicLine.strokePath();

				intermediatePoint[1] = interceptY + radius;
			} else
			{
				let b = this.scene.levelToScreenCoords(interceptX, interceptY + radius);
				graphicLine.lineTo(b.x, b.y);
				graphicLine.strokePath();

				intermediatePoint[1] = interceptY - radius;
			}

			let c = this.scene.levelToScreenCoords(interceptX, intermediatePoint[1]);
			graphicLine.moveTo(c.x, c.y);
		}

		let a = this.scene.levelToScreenCoords(interceptX, intermediatePoint[1]);
		let b = this.scene.levelToScreenCoords(interceptX, secondPoint[1]);
		graphicLine.moveTo(a.x, a.y);
		graphicLine.lineTo(b.x, b.y);

		graphicLine.strokePath();
	}


	drawWires()
	{
		this.graphicLine.clear();

		for(const wire of this.wires)
		{
			// set style of lines
			var color;
			if(this.showState == true)
			{
				var wireOn = wire.origin.getOutputState();
				color = wireOn ? LineDrawer.wireOnColor : LineDrawer.wireOffColor;
			} else
			{
				color = LineDrawer.wireOffColor;
			}

			this.graphicLine.lineStyle(this.lineWidth, color, 1.0);
			
			// Init the line starting point
			const p = wire.getPoints()[0];
			var firstPoint = [p[0], p[1]];

			this.graphicLine.beginPath();
			let a = this.scene.levelToScreenCoords(firstPoint[0], firstPoint[1]);
			this.graphicLine.moveTo(a.x, a.y);

			// Loop over all points to connect them
			for(const secondPoint of wire.getPoints())
			{
				this.checkInterceptions(firstPoint, secondPoint, this.graphicLine);
				firstPoint = [secondPoint[0], secondPoint[1]];
			}
			this.graphicLine.strokePath();
		}
	}


	destroyAssets()
	{
		this.graphicLine.destroy();
	}


	setShowState(showState)
	{
		this.showState = showState;
	}


	setMask(mask)
	{
		this.graphicLine.setMask(mask);
	}


	setDepth(depth)
	{
		this.graphicLine.setDepth(depth);
	}

	/**
	 * 
	 * @param {boolean} visibility 
	 */
	setVisible(visibility)
	{
		if(this.graphicLine.setVisible)
			this.graphicLine.setVisible(visibility);
	}

	/**
	 * Map the number x from the in range to the out range.
	 * @param {number} x The value to map.
	 * @param {number} in_min 
	 * @param {number} in_max 
	 * @param {number} out_min 
	 * @param {number} out_max 
	 * @returns x mapped to the new range.
	 */
	static map(x, in_min, in_max, out_min, out_max)
	{
		return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
	}
}

LineDrawer.wireOnColor = 0xffff00
LineDrawer.wireOffColor = 0xaaaaaa