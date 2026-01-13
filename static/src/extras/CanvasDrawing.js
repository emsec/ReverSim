/**
 * 
 */
class CanvasDrawing
{
	/**
	 * Canvas for the drawing tools. The canvas sits behind the circuit and popups.
	 * @param {BaseScene} scene 
	 */
	constructor(scene)
	{
		this.scene = scene;

		// Stuff to capture the points that were drawn
		this.lastFigure = [];
		this.isPointerDown = false;
		this.lastPointX = 0;
		this.lastPointY = 0;
	}

	preload()
	{

	}

	createObjects()
	{
		// Draws the Texture Frame to the Render Texture at the given position.
		this.rt = this.scene.add.renderTexture(0, 0, config.width, config.height);
		this.rt.setOrigin(0, 0);

		this.pencilSelector = new ToolSelector(this.scene);

		// Create color pencil buttons
		for(const color of Object.keys(pencilColors))
		{
			this.pencilSelector.appendButton(color, () => {
				// activate drawing variables
				this.draw = true;
				this.erase = false;

				this.drawLine.setStrokeStyle(4, pencilColors[color].coco); 
				this.circle.setFillStyle(pencilColors[color].coco);
				JsonRPC.send('drawSel', {"tool": pencilColors[color].logName})
			});
		}

		// Create eraser
		this.pencilSelector.appendButton('eraser2', (pointer) => {
			// activate erasing
			this.draw = false;
			this.erase = true;

			JsonRPC.send('drawSel', {"tool": "Eraser"})
		}, 0.05, 0.05);

		// Create delete button
		this.pencilSelector.appendButton('deleteButton', (pointer) => {
			// activate erasing
			this.clearRenderTexture();

			// This method is intended to print the drawing to console, to save it in order to replay it in for e.g. the IntroduceDrawingTools Scene
			// Clear all drawings
			this.lastFigure = [];

			this.deletedEverything = true;
			JsonRPC.send('drawSel', {"tool": "Delete Button"})
		}, 0.035, 0.035);

		this.pencilSelector.createObjects();

		this.drawingActive = true;
		this.draw = true;
		this.erase = false;
		this.penUsedAtLeastOnce = false;
	}

	logDrawingActions()
	{
		this.justPaintedSomething = false;
		this.erasedSomething = false;
		this.deletedEverything = false;

		this.scene.input.on('pointerup', () =>
		{
			// check if player just drew something
			if(this.justPaintedSomething == true)
			{
				//alert('dude, you painted something');
				LogData.sendCanvasPNG(this.scene);
				JsonRPC.send("draw", {"tool": "pen", "info": this.drawLine.fillColor})
				this.justPaintedSomething = false;
			} else if(this.erasedSomething == true)
			{
				//alert('you erased something');
				LogData.sendCanvasPNG(this.scene);
				JsonRPC.send("draw", {"tool": "eraser"})
				this.erasedSomething = false;
			} else if(this.deletedEverything == true)
			{
				//alert('you deleted everything')
				LogData.sendCanvasPNG(this.scene);
				JsonRPC.send("draw", {"tool": "purge"})
				this.deletedEverything = false;
			}
		});

	}

	/**
	 * Creates drawing logic.
	 */
	create()
	{
		this.createObjects();

		this.eraserForm = this.scene.add.circle(0, 0, 20, 0xffffff).setOrigin(0.5, 0.5).setVisible(false);

		this.circle = this.scene.add.circle(0, 0, 0, pencilColors['brushRed'].coco).setOrigin(0.5, 0.5);
		this.circle.setVisible(false);
		this.circle.radius = 2;
		this.drawLine = this.scene.add.line(0, 0, 0, 0, 0, 0, pencilColors['brushRed'].coco).setOrigin(0, 0);
		this.drawLine.setStrokeStyle(4, pencilColors['brushRed'].coco);
		this.drawLine.setVisible(false);

		this.eraserLine = this.scene.add.line(0, 0, 0, 0, 0, 0, 0xffffff).setOrigin(0, 0);
		this.eraserLine.setStrokeStyle(40, 0xffffff);
		this.eraserLine.setVisible(false);

		var renderActivity = false;

		// Detect if the pen was lifted
		this.scene.input.on('pointerup', () => {
			this.isPointerDown = false;
			//console.log(this.lastFigure);
		});
		this.scene.input.on('pointermove', (pointer) =>
		{
			if(pointer.leftButtonDown())
			{
				renderActivity = true;

				var points = pointer.getInterpolatedPosition(10);

				// If the pen was lifted, do not connect to the last captured point
				if(!this.isPointerDown)
				{
					this.lastPointX = points[0].x;
					this.lastPointY = points[0].y;
				}

				// check if mouse is under drawing tools
				var gameObjects = this.scene.input.hitTestPointer(pointer);
				for(var obj of gameObjects)
				{
					var type = obj.type;

					if(type == null)
						continue;

					if(type == 'Rectangle' || type == 'Image')
						return;
				}

				if(this.draw && !this.erase && this.drawingActive)
				{
					this.penUsedAtLeastOnce = true;
					this.justPaintedSomething = true;

					// This method is intended to print the drawing to console, to save it in order to replay it in for e.g. the IntroduceDrawingTools Scene
					if(false)
					{
						if(!this.isPointerDown)
							this.lastFigure[this.lastFigure.length] = points;	
						else
							this.lastFigure[this.lastFigure.length-1] = this.lastFigure[this.lastFigure.length-1].concat(points);

						let currentMillis = Date.now();
						if(currentMillis - this.lastDrawing > 5000)
							

						this.lastDrawing = currentMillis;
					}

					// Have to use call(...), otherwise 'this' is messed up
					let lastPoints = this.drawPoints.call(this, points, this.lastPointX, this.lastPointY);
					this.lastPointX = lastPoints.x;
					this.lastPointY = lastPoints.y;

				} else if(!this.draw && this.erase && this.drawingActive)
				{
					this.erasedSomething = true;

					points.forEach((p) =>
					{
						this.eraserForm.x = p.x;
						this.eraserForm.y = p.y;

						this.eraserLine.setTo(this.lastPointX, this.lastPointY, p.x, p.y);
						this.rt.erase(this.eraserForm, pointer.x, pointer.y);
						// TODO add line eraser and not only erase in a circle

						// save last points 
						this.lastPointX = p.x;
						this.lastPointY = p.y;

						this.eraserForm.setVisible(true);
					}, this);
				}

				this.isPointerDown = true;
			}
		}, this);

		this.scene.input.on('pointerup', () =>
		{
			this.eraserForm.setVisible(false);

			if(renderActivity)
				renderActivity = false;
		}, this);

		this.scene.input.on('gameout', () =>
		{
			this.eraserForm.setVisible(false);
		});
	}

	/**
	 * Draw the specified array of points to the canvas. 
	 * @param {*} points An array of points `p.x`, `p.y` to draw.
	 * @param {number} lastPointX Specify the start x-coordinate to draw the line from. If omitted, it will use the first coordinate from points.
	 * @param {number} lastPointY Specify the start y-coordinate to draw the line from. If omitted, it will use the first coordinate from points.
	 */
	drawPoints(points, lastPointX = points[0].x, lastPointY = points[0].y)
	{
		points.forEach(function (p)
		{
			// draw lines 
			this.circle.setPosition(p.x, p.y);
			this.rt.draw(this.circle);

			this.drawLine.setVisible(false);
			this.drawLine.setTo(lastPointX, lastPointY, p.x, p.y);
			this.rt.draw(this.drawLine);

			// save last points 
			lastPointX = p.x;
			lastPointY = p.y;
		}, this);

		return { 'lastPointX': lastPointX, 'lastPointY': lastPointY };
	}

	/**
	 * Allows drawing on canvas
	 */
	activateDrawing()
	{
		this.drawingActive = true;
		this.pencilSelector.setEnabled(true);
	}

	/**
	 * Deactivates drawing.
	 */
	deactivateDrawing()
	{
		this.drawingActive = false;
		this.pencilSelector.setEnabled(false);
	}

	/**
	 * Destroys assets.
	 */
	cleanUp()
	{
		this.pencilSelector.cleanUp();
		this.pencilSelector.destroy();
		this.rt.destroy();
	}

	/**
	 * Deletes drawing.
	 */
	clearRenderTexture()
	{
		// The bug in `this.rt.texture` where width, height, dirty where -1 or false was fixed
		this.rt.clear();
	}

	setVisible(bool)
	{
		this.drawingActive = bool;
		this.pencilSelector.setVisible(bool);
	}
}

// https://gist.github.com/mwaskom/b35f6ebc2d4b340b4f64a4e28e778486
const pencilColors = {
	"brushRed": {
		"logName": "Red",
		"coco": 0xE20048
	},
	"brushGreen": {
		"logName": "Green",
		"coco": 0xCCF600
	},
	"brushBlue": {
		"logName": "Blue",
		"coco": 0x0034AB
	}
}