/**
 * 
 */
class Layouter
{
	constructor(scene, levelElements)
	{
		this.levelElements = levelElements;
	}


	gridDist(pointA, pointB)
	{
		return Math.abs(pointA.x - pointB.x) + Math.abs(pointA.y - pointB.y)
	}


	computeOutputWire()
	{
		const GRID_SIZE = Layouter.GRID_SIZE;
		var wires = new Array();
		var occupiedPoints = new Set();

		let key = null;
		try
		{
			// mark position of elements as occupied
			for(key in this.levelElements)
			{
				var x = this.levelElements[key];
				occupiedPoints.add(x.getPos().getPos());

				// set some points to occupied 
				if(x instanceof AndGate || x instanceof OrGate || x instanceof Inverter || x instanceof CovertGate)
				{
					var intermediatePoint = this.getParallelPos(x, x.getOutputPort().x, x.getOutputPort().y, 0, -25);
					occupiedPoints.add(intermediatePoint.getPos());
				}
			}

			// go through every element and determine the wire way to their destinations
			for(key in this.levelElements)
			{
				var x = this.levelElements[key];

				for(const target of x.getOutputs())
				{
					var watchdog = 0;

					var wire = new Wire(x);

					var start = new Point(x.getOutputPort().x, x.getOutputPort().y);
					// add starting point
					wire.addPoint(start);
					occupiedPoints.add(start.getPos());

					// manage output ports of target
					if(x instanceof AndGate || x instanceof OrGate || x instanceof CovertGate)
					{
						var intermediatePoint = this.getParallelPos(x, start.x, start.y, 0, -25);
						wire.addPoint(intermediatePoint);
						start = intermediatePoint;
					} else if(x instanceof Inverter)
					{
						var intermediatePoint = this.getParallelPos(x, start.x, start.y, 0, -25);
						wire.addPoint(intermediatePoint);
						start = intermediatePoint;
					}

					var p = new Point(start.x, start.y);

					var end = target.getInputPort(x);
					var endPort = null;

					// manage input ports of target
					if(target instanceof AndGate || target instanceof OrGate)
					{
						endPort = target.getInputPort(x);
						end = this.getParallelPos(target, end.x, end.y, 0, 50);
					} else if(target instanceof DangerSign || target instanceof LightBulb || target instanceof Inverter || target instanceof VCC)
					{
						endPort = target.getInputPort(x);
						end = this.getParallelPos(target, target.x, target.y, 0, 25);
					} else if(target instanceof CovertGate)
					{
						endPort = target.getInputPort(x);

						if(target.camouflageElementImage == 'inverter')
						{
							end = this.getParallelPos(target, end.x, end.y, 0, 25);
						} else
						{
							end = this.getParallelPos(target, end.x, end.y, 0, 50);
						}
					} else
					{
						end = target.getInputPort(x);
					}

					while(!p.equals(end))
					{
						if(watchdog++ > 100)
						{
							console.log('Layouter failed: No wire way found');
							return new Array();
						}

						var origin = new Point(p.x, p.y);

						// determine distance
						var xDist = end.x - p.x;
						var yDist = end.y - p.y;

						// find the current direction which is determined by the highest distance
						var xDirection = 0;
						var yDirection = 0;
						if(Math.abs(xDist) > Math.abs(yDist))
						{
							if(xDist > 0)
							{
								xDirection = 1;
							} else
							{
								xDirection = -1;
							}
						} else
						{
							if(yDist > 0)
							{
								yDirection = 1;
							} else
							{
								yDirection = -1;
							}
						}

						// walk the current direction until target or obstacle is reached
						while((xDist != 0 && xDirection != 0) || (yDist != 0 && yDirection != 0))
						{

							if(watchdog++ > 100)
							{
								console.log('Layouter timeout');
								return new Array();
							}

							// buffer current point
							var oldPos = new Point(p.x, p.y);

							// determine new possible point
							p.x += xDirection * Math.min(GRID_SIZE, Math.abs(xDist));
							p.y += yDirection * Math.min(GRID_SIZE, Math.abs(yDist));

							// discard new point if its too close to another point or element
							if(!p.equals(end))
							{
								var tooClose = false;
								for(const key in this.levelElements)
								{
									var e = this.levelElements[key];

									if(e instanceof Splitter) continue;
									if(e.getPos().distance(p) < GRID_SIZE / 2)
									{
										tooClose = true;
									}
								}
								if(this.pointInSet(p.x, p.y, occupiedPoints) || tooClose)
								{
									p.x = oldPos.x;
									p.y = oldPos.y;
									break;
								}
							}
							// determine distances again
							xDist = end.x - p.x;
							yDist = end.y - p.y;
						}
						// if the last point was not too close to another element or point
						// and if it is a new point, than add it to the array
						if(!p.equals(origin))
						{
							wire.addPoint(p);
						} else
						{
							// shortest way was not possible so try a slight detour
							xDist = Math.min(GRID_SIZE, Math.abs(xDist));
							yDist = Math.min(GRID_SIZE, Math.abs(yDist));
							if(xDist == 0) xDist = GRID_SIZE;
							if(yDist == 0) yDist = GRID_SIZE;

							// determine four new points surrounding last valid point
							var alternates = new Array();
							if(yDirection != 0)
							{
								alternates.push(new Point(p.x + xDist, p.y));
								alternates.push(new Point(p.x - xDist, p.y));
							} else
							{
								alternates.push(new Point(p.x, p.y + yDist));
								alternates.push(new Point(p.x, p.y - yDist));
							}

							// determine point with the shortest distance to the end
							var minDist = Number.MAX_SAFE_INTEGER;
							for(const a of alternates)
							{
								var dist = this.gridDist(a, end);
								if(this.pointInSet(a.x, a.y, occupiedPoints)) dist += 2 * GRID_SIZE;
								if(dist < minDist)
								{
									minDist = dist;
									p.x = a.x;
									p.y = a.y;
								}
							}
							wire.addPoint(p);
						}
						occupiedPoints.add(p.getPos());
					}

					// connect last point to input port
					if(endPort != null)
					{
						// manage end port
						wire.addPoint(endPort);
						occupiedPoints.add(endPort.getPos());
					}

					wires.push(wire);
					x.wires.push(wire);
				}
			}
		}
		catch(error)
		{
			// Circuit errors already contain all relevant information, bubble up
			if(error instanceof CircuitError)
				throw error;
			
			// Make a guess which element might have caused the error and trow the original exception
			error.faultyElement = Number(key);
			throw error;
		}

		return wires;
	}


	getParallelPos(element, x, y, deltaX, deltaY)
	{
		// rotation in radian
		var angle = (element.rotation - 1) * 90 * Math.PI / 180;

		// calculate (x,y)-Coordinate of port in relation to the element
		var portX = x + deltaX * Math.cos(angle) - deltaY * Math.sin(angle);
		var portY = y + deltaY * Math.cos(angle) + deltaX * Math.sin(angle);

		return new Point(portX, portY);
	}


	pointInSet(x, y, set)
	{
		var pointCoordinates = Array.from(set);

		for(const coordinates of pointCoordinates)
		{
			if(x == coordinates[0])
			{
				if(y == coordinates[1]) return true;
			}
		}
		return false;
	}
}

Layouter.GRID_SIZE = 50;