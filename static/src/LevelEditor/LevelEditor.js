/**
 * Level coordinates are called xPos / yPos, screen coordinates x / y.
 */
class LevelEditor extends LevelViewScene
{
	/**
	 * Create a level editor
	 */
	constructor()
	{
		super("LevelEditor");
		this.marginFac = 1; // Enable level margins by setting the margin factor to 1
		this.showIDs = false;

		this.activeMode = LEVEL_EDITOR_MODE.SELECT;

		// Contains the last selected element
		this.selectedElement = null;
		this.selectedWireHighlight = null;
		this.elementTypeToPlace = null;

		// Contains the object which was under the cursor on pointer down (if any). Will become null after pointer up.
		this.draggedElement = null; // ad
		this.levelFile = null;

		/** Game objects for the WireMode, these will be deleted after the user leaves wire mode. */
		this.wireModeGameObjects = [];
	}

	// @Override
	preload()
	{
		this.load.image('arrow_upleft', 'res/images/arrow_upleft.png');
		this.load.image('text', 'res/images/text.png');
	}

	// @Override
	createElements(setting)
	{
		// Register input listeners
		this.input.keyboard.on('keydown-' + 'ESC', () => {
			this.resetEditorMode();
		});

		this.input.keyboard.on('keydown-' + 'R', this.rotateActiveComponent);

		// Create a grid
		let grid = this.drawGrid(LevelEditor.gridWidth, LevelEditor.gridHeight, LevelEditor.gridIncrements);
		grid.setInteractive();
		grid.setData('type', 'gridAction');
		this.grid = grid;

		// Create toolbar
		this.toolbar = new ToolSelector(this);
		this.toolbar.xOffset = 30;
		this.toolbar.initialYOffset = 10;
		this.toolbar.yOffset = 45;
		this.toolbar.appendButton('arrow_upleft', () => {
			this.changeMode(LEVEL_EDITOR_MODE.SELECT)
		}, 0.3, 0.3);
		this.toolbar.appendButton('wireConnection', () => {
			this.changeMode(LEVEL_EDITOR_MODE.CONNECT)
		});

		// Append placable components
		for(let component in LevelElement.elementTypes)
		{
			// Callback when a toolbar button gets pressed
			this.toolbar.appendButton(LevelElement.getComponentIcon(component), () => {
				this.elementTypeToPlace = component;
				this.changeMode(LEVEL_EDITOR_MODE.PLACE);
			});
		}
		this.toolbar.createObjects();

		// Create error message
		this.errorMessage = this.drawText('Loading ...', 90, 20);

		// Create Circuit
		if(this.levelFile == null)
			this.loadLevelFromUrl('assets/levels/elementIntroduction/hre_editor_level.txt');
		else
			this.updateCircuit();

		// Also accept clicks on gameObjects which are not on top / make transparent to clicks
		this.input.setTopOnly(true);

		// Create properties panel
		this.propertiesPanel = new PropertiesPanel(this);
		this.propertiesPanel.hide();

		// Create Buttons
		let btnPlay = new RectButton(this, 0, 0, 'play', 'right', 'testPlayButton');
		let btnOpen = new RectButton(this, 0, 0, 'open', 'right', 'openButton');
		let btnSave = new RectButton(this, 0, 0, 'save', 'right', 'saveButton');
		let btnNew = new RectButton(this, 0, 0, 'newLevel', 'right', 'newLevelButton');
		this.buttonPanel = new ButtonBar(this, [btnSave, btnOpen, btnPlay, btnNew], config.width - 20, config.height*0.88, ButtonBarAlignment.RIGHT);

		for(let b of this.buttonPanel.buttons)
			b.setDepth(1000);

		this.input.on('pointermove', this.onPointerMove, this);

		// Create button callbacks
		this.registerClickListener("testPlayButton", this.onLevelPlay);
		this.registerClickListener("openButton", this.onLevelOpen);
		this.registerClickListener("saveButton", this.onLevelSave);
		this.registerClickListener("newLevelButton", this.onNewLevel);
		this.registerClickListener("deleteWire", this.onWireDelete);
		this.registerClickListener("wireSelect", this.selectWire);

		// Create error highlight
		this.errorHighlight = this.add.circle(0, 0, LevelEditor.elementSelectDistance + 5, 0xFF4422);
		this.errorHighlight.setVisible(false);

		// Create connection highlight
		this.selectedWireHighlight = this.add.graphics();

		this.informationBar.setDocumentationVisible(true);
	}

	// @Override
	onPointerDown(pointer, localX, localY, gameObjects)
	{
		let offset = LevelEditor.screenToLevelCoords(pointer.x, pointer.y, this.marginFac);
		this.draggedElement = this.levelFile.getByPosition(offset.xPos, offset.yPos, LevelEditor.elementSelectDistance);
		switch(this.activeMode)
		{
			case LEVEL_EDITOR_MODE.SELECT:
			case LEVEL_EDITOR_MODE.PLACE:
				this.releaseElement();
				this.selectElement(this.draggedElement);
				break;
		}
		
		super.onPointerDown(pointer, localX, localY, gameObjects);
	}

	/**
	 * https://newdocs.phaser.io/docs/3.54.0/Phaser.Input.Events
	 * @param {Phaser.Input.Pointer} pointer 
	 * @param {Phaser.GameObjects.GameObject[]} currentlyOver 
	 * @returns 
	 */
	onPointerMove(pointer, currentlyOver)
	{
		if(this.draggedElement == null)
			return;

		switch(this.activeMode)
		{
			case LEVEL_EDITOR_MODE.SELECT:
			case LEVEL_EDITOR_MODE.PLACE:
				const levelPos = LevelEditor.screenToLevelCoords(pointer.x, pointer.y);
				const gridPos = LevelEditor.snapToGrid(levelPos.xPos, levelPos.yPos);
				this.moveGateIcon(this.draggedElement, levelPos.xPos, levelPos.yPos, 0.3);
				break;
		}
	}

	// @Override
	onPointerUp(pointer, localX, localY, gameObjects)
	{
		const offset = LevelEditor.screenToLevelCoords(pointer.x, pointer.y, this.marginFac);
		const gridPos = LevelEditor.snapToGrid(offset.xPos, offset.yPos);
		let releasedElement = this.levelFile.getByPosition(gridPos.xPos, gridPos.yPos, LevelEditor.elementSelectDistance);

		switch(this.activeMode)
		{
			// Check if we can place a component, otherwise fall through to SELECT mode
			case LEVEL_EDITOR_MODE.PLACE:
				// If the player clicked outside of the Grid fall through to SELECT Mode
				if(this.input.hitTestPointer(pointer).includes(this.grid) && this.draggedElement == null)
				{
					// If the player clicked an empty spot place the component, otherwise fall through
					if(this.levelFile.getByPosition(gridPos.xPos, gridPos.yPos) == null)
					{
						// After an element was placed, create a new one
						this.selectedElement = this.createComponent(this.elementTypeToPlace);
						this.placeActiveComponent(gridPos.xPos, gridPos.yPos, true);
						break;
					}
				}

			case LEVEL_EDITOR_MODE.SELECT:
				// If the element was dragged, move it to the new position
				if(this.draggedElement != releasedElement)
					this.placeActiveComponent(offset.xPos, offset.yPos, false);

				// If the user clicked in the void, deselect current element
				else if(releasedElement == null)
					this.releaseElement();
				
				// Show the properties panel on the selected object
				else if(this.selectedElement != null)
					this.showPropertiesPanel(this.selectedElement, pointer.x, pointer.y);

				// Reset transparency, if the element was dragged
				// Also make sure the position is consistent with the level state
				if(this.draggedElement instanceof LevelElement)
				{
					try {
						this.moveGateIcon(
							this.draggedElement,
							this.draggedElement.xPos, this.draggedElement.yPos,
							1.0
						);
					}
					catch(e) {
						console.error(e);
					}
				}
				
				break;

			case LEVEL_EDITOR_MODE.CONNECT:
				// Wire up component if something was selected, otherwise this method does nothing
				this.wireUpComponent(releasedElement);				
				break;
		}
		
		this.draggedElement = null;
		super.onPointerUp(pointer, localX, localY, gameObjects);
	}

	/**
	 * Change currently selected tool/mode of the LevelEditor
	 * @param {string} newMode 
	 */
	changeMode(newMode)
	{
		if(!Object.keys(LEVEL_EDITOR_MODE).includes(newMode))
			throw 'Unknown Level Editor mode "' + newMode + '"!';

		this.releaseElement();

		if(this.activeMode == LEVEL_EDITOR_MODE.CONNECT)
			this.leaveWireMode();

		switch(newMode)
		{
			case LEVEL_EDITOR_MODE.SELECT:
				break;

			case LEVEL_EDITOR_MODE.PLACE:
				break;

			case LEVEL_EDITOR_MODE.CONNECT: 
				this.enterWireMode();
				break;
		}

		this.activeMode = newMode;
	}

	/**
	 * The Original Java HRE Game grid goes from (0, 0) to ~(1250, 700) in 50u increments
	 */
	drawGrid(width=1250, height=700, increments=50)
	{
		const color = 0x9966ff;
		let rect = this.drawRect(0, 0, width, height, color, 2);

		// Add vertical lines
		for(let x=increments; x<width; x+=increments)
			this.drawLine(x, 0, x, height, color, 1, 0.5);
		
		// Add horizontal lines
		for(let y=increments; y<height; y+=increments)
			this.drawLine(0, y, width, y, color, 1, 0.5);

		return rect;
	}

	drawLine(x1, y1, x2, y2, color, lineWidth=1, alpha=1)
	{
		const begin = LevelEditor.levelToScreenCoords(x1, y1, this.marginFac);
		const end = LevelEditor.levelToScreenCoords(x2, y2, this.marginFac);

		let line = this.add.line(0, 0, begin.x, begin.y, end.x, end.y);
		line.setOrigin(0, 0);
		line.setStrokeStyle(lineWidth, color, alpha);

		return line;
	}

	// @Override
	next() {}

	/**
	 * 
	 * @param {LevelLine} selectedElement 
	 */
	selectElement(selectedElement)
	{
		if(!(selectedElement instanceof LevelElement))
			return;

		this.selectedElement = selectedElement;

		try {
			this.getGuiElementByComponentId(selectedElement).setHighlighted(true);
		}
		catch(e) {
			console.log(e);
		}
	}

	/**
	 * 
	 * @param {Phaser.GameObjects.Line} gameObject 
	 */
	selectWire(gameObject)
	{
		// Deselect any old wire if any
		if(this.selectedWireHighlight)
			this.selectedWireHighlight.clear();

		const con = gameObject.getData('connection');

		this.selectedWireHighlight.lineStyle(LevelEditor.lineSelectDistance*2, LevelEditor.colorSelected, LevelEditor.transparencySelected);
		for(let line of con.getConnectionCoords())
		{
			const begin = this.levelToScreenCoords(line.x1, line.y1);
			const end = this.levelToScreenCoords(line.x2, line.y2);

			this.selectedWireHighlight.moveTo(begin.x, begin.y);
			this.selectedWireHighlight.lineTo(end.x, end.y);
		}
		this.selectedWireHighlight.stroke();

		this.showPropertiesPanel(con, 0, 0);
	}

	releaseElement()
	{
		try {
			// Unselect the currently selected element (this might be none or not added to the circuit)
			if(this.selectedElement instanceof LevelElement)
			{
				const e = this.getGuiElementByComponentId(this.selectedElement)

				if(e != null)
					e.setHighlighted(false);
			}
		}
		catch(e) {
			console.log(e);
		}
		
		this.propertiesPanel.hide();
		this.selectedElement = null;

		// Deselect any old wire if any
		if(this.selectedWireHighlight)
			this.selectedWireHighlight.clear();
	}

	// @Override
	updateCircuit()
	{
		this.errorMessage.setText(""); // Clear the error message
		this.errorHighlight.setVisible(false);

		this.clearComponentAnchors();

		super.updateCircuit();
	}

	/**
	 * Factory to create a LevelElement with an automatic id and its default parameters
	 * initialized. You can then adjust position or other params as needed.
	 * @param {string} type One of `LevelElement.elementTypes`
	 */
	createComponent(type)
	{
		return new LevelElement(
			type, this.levelFile.nextElementID(), -1, 0, 0, 
			LevelElement.getDefaultParams(type)
		);
	}

	/**
	 * 
	 * @param {number} xpos X-Position of the element in level coordinates
	 * @param {number} ypos Y-Position of the element in level coordinates
	 * @returns 
	 */
	placeActiveComponent(xpos, ypos, createNew = true)
	{
		if(!(this.selectedElement instanceof LevelElement))
			return;

		try
		{
			this.moveActiveComponent(xpos, ypos);

			if(createNew)
				this.levelFile.appendComponent(this.selectedElement);
			else
				this.levelFile.writeFile();
		}
		catch(e)
		{
			console.log("Unable to release element: " + e);
		}

		this.updateCircuit();
		this.releaseElement();
	}

	/**
	 * Move component around the grid, altering the loaded level state.
	 * 
	 * A redraw is needed to show the changes, see `this.updateCircuit()`.
	 * @param {number} xPos X-Position of the element in level coordinates
	 * @param {number} yPos Y-Position of the element in level coordinates
	 */
	moveActiveComponent(xPos, yPos)
	{
		const newPos = LevelEditor.snapToGrid(xPos, yPos);

		if(this.levelFile.getByPosition(newPos.xPos, newPos.yPos) != null)
			throw new Error("Positions overlap");

		this.selectedElement.xPos = newPos.xPos;
		this.selectedElement.yPos = newPos.yPos;
	}

	rotateActiveComponent()
	{
		if(this.selectedElement instanceof LevelElement)
			this.selectedElement.rotate();
	}

	/**
	 * Move an icon visually without altering the level file
	 * Mainly used by `onPointerMove()` to give visual feedback where the gate will be placed.
	 * 
	 * @param {LevelElement} draggedElement The LevelElement which icon we wanna move visually
	 * @param {number} levelX Position of the gate in screen coordinates
	 * @param {number} levelY Position of the gate in screen coordinates
	 * @param {number} [alpha=0.3] Transparency of the icon
	 * @returns The screen coordinates of the gate snapped onto the grid
	 */
	moveGateIcon(draggedElement, levelX, levelY, alpha = 0.3)
	{
		if(! (draggedElement instanceof LevelElement))
			return;

		const gridPos = LevelEditor.snapToGrid(levelX, levelY);
		const screenPos = LevelEditor.levelToScreenCoords(gridPos.xPos, gridPos.yPos);
		const goj = this.getGuiElementByComponentId(draggedElement);

		try {
			goj.setAlpha(alpha);
			goj.getActiveImage().setPosition(screenPos.x, screenPos.y);
		}
		catch(e) {
			console.error(e);
		}

		return screenPos;
	}

	enterWireMode()
	{
		let connections = this.levelFile.getConnections();
		const wireTransparency = 0.6;

		// Visualize all connections
		for(let c of connections)
		{
			for(let line of c.getConnectionCoords())
			{
				const wireColor = c.isCovertGate() ? LevelEditor.colorCovertWire : LevelEditor.colorWire;

				const l = this.drawLine(line.x1, line.y1, line.x2, line.y2, wireColor, LevelEditor.wireWidth, wireTransparency);
				this.wireModeGameObjects.push(l);
				this.wireModeGameObjects.push(new WireDeleteButton(this, line));

				l.setData('type', 'wireSelect');
				l.setData('connection', c);
				l.setData('line', line);
				l.setInteractive(new LineHitbox(l.geom.x1, l.geom.y1, l.geom.x2, l.geom.y2, LevelEditor.lineSelectDistance), LineHitbox.Contains);

				l.on('pointerover', (e) => l.setStrokeStyle(LevelEditor.wireWidth, LevelEditor.colorSelected));
				l.on('pointerout', (e) => l.setStrokeStyle(LevelEditor.wireWidth, wireColor, wireTransparency));
			}
		}

		this.circuit.wireDrawer.setVisible(false);
	}

	leaveWireMode()
	{
		for(let o of this.wireModeGameObjects)
			o.destroy();
		
		this.wireModeGameObjects = [];

		this.circuit.wireDrawer.setVisible(true);
	}

	onWireDelete(gameObject)
	{
		this.deleteWire(gameObject.getData('line'));
	}

	deleteWire(line)
	{
		this.levelFile.deleteWire(line.id1, line.id2);
		this.leaveWireMode();
		this.updateCircuit();
		this.enterWireMode();
	}

	/**
	 * The first call will select the first component to hook up, the second call will 
	 * then connect it to the currently selected element.
	 * Pass null to release the previously selected element.
	 * @param {LevelElement} levelElement 
	 */
	wireUpComponent(levelElement)
	{
		// A click on empty space will deselect the last element
		if(!(levelElement instanceof LevelElement))
		{
			this.releaseElement();
			return;
		}

		// If a component was previously selected, connect it with the current one (If they are not the same).
		if(this.selectedElement instanceof LevelElement)
		{
			if(this.selectedElement.id == levelElement.id)
				console.error("Cannot wire up a component with itself!");
			else
			{
				let existingConnection = this.levelFile.getConnectionByStartID(this.selectedElement.id);
				if(existingConnection != null && !existingConnection.isCovertGate())
				{
					existingConnection.addConnection(levelElement);
					this.levelFile.writeFile();
				}
				else
					this.levelFile.appendComponent(new LevelConnection(this.selectedElement, [levelElement]));

				this.updateCircuit();
				this.leaveWireMode();
				this.enterWireMode();
			}

			this.releaseElement();
		}
		else
			this.selectElement(levelElement);
	}

	/**
	 * 
	 * @param {LevelLine} element 
	 * @param {number} localX
	 * @param {number} localY
	 */
	showPropertiesPanel(element, localX, localY)
	{
		if(element instanceof LevelElement)
			this.propertiesPanel.addHeader(element.type + " (#" + element.id + ")");
		else
			this.propertiesPanel.addHeader(element.key);

		this.propertiesPanel.addCircuitElement(element, (value, name) => {
			// Should always be LevelElement, but just to be sure
			if(!(element instanceof LevelElement))
				return;
			
			// Update the properties and circuit
			element.setProperty(name, value);
			this.levelFile.writeFile();
			this.updateCircuit();
		});

		this.propertiesPanel.propertiesList.appendChild(document.createElement('hr'));

		// Add delete button
		this.propertiesPanel.addButton("Delete", () => {
			this.releaseElement();
			this.levelFile.deleteComponent(element);
			this.updateCircuit();
		});

		if(element instanceof LevelConnection)
		{
			const isCovert = element.isCovertGate();

			if(isCovert || this.levelFile.isCovertWireCandidate(element))
			{
				const switchTo = isCovert ? 'normal' : 'covert';
				this.propertiesPanel.addButton("Make " + switchTo + " connection", () => {
					element.setConnectionType(!isCovert);
					this.leaveWireMode();
					this.propertiesPanel.hide();
					this.selectedWireHighlight.clear();
					this.levelFile.writeFile();
					this.updateCircuit();
					this.enterWireMode();
				});
			}
		}

		this.propertiesPanel.show();

		const xOrigin = localX < config.width/2 ? 0 : 1;
		const yOrigin = localY < config.height/2 ? 0 : 1;
		this.propertiesPanel.setOrigin(xOrigin, yOrigin);
		this.propertiesPanel.setPosition(localX, localY);
	}

	/**
	 * Test run the level
	 */
	onLevelPlay()
	{
		// Enter select mode, since after returning from the level the ui will be reset
		this.resetEditorMode();

		console.log("Testing level");
		AniLib.darkenScreen(this, () => {
			this.nextPhase('Competition', {
				levelName: this.levelFile.fileContent,
				levelType: 'localLevel'
			});
		});
	}

	onLevelOpen()
	{
		console.log("Opening file chooser dialogue");
		let tmpFileChooser = document.createElement('input');
		tmpFileChooser.type = 'file';
		tmpFileChooser.onchange = (e) => {
			let file = tmpFileChooser.files[0];
			console.log(`Opening "${file.name}" (size ${(file.size/1024).toFixed(2)}KB).`);

			const reader = new FileReader();
			reader.readAsArrayBuffer(file.slice(0, 1024 * 10));
			reader.onload = (e) => {
				if(e.target.result instanceof ArrayBuffer)
				{
					const enc = new TextDecoder(config.LEVEL_ENCODING);
					this.loadLevel(file.name, enc.decode(e.target.result));
				}
				else
					this.loadLevel(file.name, e.target.result);				
			};
		};
		tmpFileChooser.click();
	}

	/**
	 * Download the current level to the users disk
	 */
	onLevelSave()
	{
		const fileName = this.levelFile.fileName.toLowerCase();
		console.log(`Saving file to "${fileName}".`);

		// https://code.tutsplus.com/tutorials/how-to-save-a-file-with-javascript--cms-41105
		let tempLink = document.createElement("a");
		// @ts-ignore There is no way to specify the encoding in a Blob, you need a library for that...
		const file = new Blob([this.levelFile.saveFile()], {type: 'text/plain'});

		tempLink.setAttribute('href', URL.createObjectURL(file));
		tempLink.setAttribute('download', fileName);
		tempLink.click();

		URL.revokeObjectURL(tempLink.href);
	}

	onNewLevel()
	{
		const newLevelName = "new_hre_level.txt";

		if(this.levelFile.isDirty())
		{
			console.log("Level contains unsaved changes, asking for confirmation to delete everything.");
			let reallyDeleteAll = confirm(LangDict.get('unsavedChanges'));

			if(reallyDeleteAll)
				this.loadLevel(newLevelName, LevelFile.createEmpty());	
		}
		else
			this.loadLevel(newLevelName, LevelFile.createEmpty());
	}

	//@Override
	loadLevel(levelName, data)
	{
		// Switch to select mode after loading a level, since
		// there might be no wires afterwards
		this.resetEditorMode();

		// Call super method
		super.loadLevel(levelName, data);
	}

	/**
	 * Reset the level editor mode to the default `LEVEL_EDITOR_MODE.SELECT`
	 */
	resetEditorMode()
	{
		this.changeMode(LEVEL_EDITOR_MODE.SELECT);
		const firstElement = this.toolbar.interactiveObjects[0];
		this.toolbar.repositionRect(firstElement);
	}

	/**
	 * 
	 * @param {LevelElement} component 
	 * @returns {Component}
	 */
	getGuiElementByComponentId(component)
	{
		return this.circuit.elementsManager.levelElements[component.id];
	}

	clearComponentAnchors()
	{
		for(let o of this.circuitGameObjects)
			o.destroy();
		this.circuitGameObjects = [];
	}

	cleanUp()
	{
		this.toolbar.cleanUp();
	}

	static snapToGrid(xPos, yPos)
	{
		xPos = Math.round(xPos / LevelEditor.gridIncrements) * LevelEditor.gridIncrements;
		yPos = Math.round(yPos / LevelEditor.gridIncrements) * LevelEditor.gridIncrements;

		// Ensure element is dragged inside view
		xPos = Math.max(0, Math.min(xPos, LevelEditor.gridWidth));
		yPos = Math.max(0, Math.min(yPos, LevelEditor.gridHeight));
		return {xPos: xPos, yPos: yPos};
	}
}

LevelEditor.gridWidth = 1250;
LevelEditor.gridHeight = 700;
LevelEditor.gridIncrements = Layouter.GRID_SIZE;

LevelEditor.elementSelectDistance = 30;
LevelEditor.lineSelectDistance = 10;

LevelEditor.wireWidth = 3;

LevelEditor.colorSelected = highlightColor;
LevelEditor.colorHelperElements = 0xFFAA00;
LevelEditor.colorWire = 0x00FF00;
LevelEditor.colorCovertWire = 0xFF7115;

LevelEditor.transparencySelected = highlightTransparency;

const LEVEL_EDITOR_MODE = {
	SELECT: 'SELECT',
	CONNECT: 'CONNECT',
	PLACE: 'PLACE'
};

class LineHitbox extends Phaser.Geom.Line
{
	/**
	 * 
	 * @param {number} x1 The x coordinate of the lines starting point.
	 * @param {number} y1 The y coordinate of the lines starting point.
	 * @param {number} x2 The x coordinate of the lines ending point.
	 * @param {number} y2 The y coordinate of the lines ending point.
	 * @param {number} distance 
	 */
	constructor(x1, y1, x2, y2, distance)
	{
		super(x1, y1, x2, y2);
		this.distance = distance;

		this.bounds = {
			minX: x1 < x2 ? x1 - distance : x2 - distance,
			minY: y1 < y2 ? y1 - distance : y2 - distance,
			maxX: x1 > x2 ? x1 + distance : x2 + distance,
			maxY: y1 > y2 ? y1 + distance : y2 + distance
		}
	}

	/**
	 * 
	 * @param {number} x 
	 * @param {number} y 
	 * @return {boolean} `true` if the distance of the point to the line is less than `this.distance`, otherwise `false`.
	 */
	contains(x, y)
	{
		return LineHitbox.Contains(this, x, y, null);
	}

	/**
	 * https://github.com/photonstorm/phaser3-examples/blob/master/public/src/input/game%20object/custom%20shape%20hit%20area.js
	 * @param {LineHitbox} lineHitbox 
	 * @param {number} x 
	 * @param {number} y
	 * @param {Phaser.GameObjects.GameObject} gameObject
	 * @returns {boolean}
	 */
	static Contains(lineHitbox, x, y, gameObject)
	{
		if(x < lineHitbox.bounds.minX || x > lineHitbox.bounds.maxX)
			return false;

		if(y < lineHitbox.bounds.minY || y > lineHitbox.bounds.maxY)
			return false;

		const dist = ( Math.abs((lineHitbox.x2 - lineHitbox.x1)*(lineHitbox.y1 - y) - (lineHitbox.x1 - x)*(lineHitbox.y2 - lineHitbox.y1)) 
				/ Math.sqrt(Math.pow(lineHitbox.x2 - lineHitbox.x1, 2) + Math.pow(lineHitbox.y2 - lineHitbox.y1, 2)) );

		return dist <= lineHitbox.distance;
	}
}

class WireDeleteButton extends Phaser.GameObjects.GameObject
{
	/**
	 * 
	 * @param {LevelEditor} scene 
	 * @param {*} line
	 */
	constructor(scene, line)
	{
		super(scene, 'WireDeleteButton');
		const deleteButtonEndDistance = 40;
		const normalColor = 0xFF3333;

		const lineStart = scene.levelToScreenCoords(line.x1, line.y1);
		const lineEnd = scene.levelToScreenCoords(line.x2, line.y2);

		// Calculate position of button
		let dirX = lineStart.x - lineEnd.x;
		let dirY = lineStart.y - lineEnd.y;
		
		const magnitude = Math.sqrt(Math.pow(dirX, 2) + Math.pow(dirY, 2));
		dirX = dirX / magnitude * deleteButtonEndDistance;
		dirY = dirY / magnitude * deleteButtonEndDistance;

		const finalPos = {x: lineEnd.x + dirX, y: lineEnd.y + dirY};

		// Create UI
		this.circle = scene.add.circle(finalPos.x, finalPos.y, 7, normalColor);
		this.loj1 = scene.add.line(finalPos.x, finalPos.y, -5, -5, 5, 5, 0x0);
		this.loj2 = scene.add.line(finalPos.x, finalPos.y, 5, -5, -5, 5, 0x0);
		this.loj1.setOrigin(0, 0);
		this.loj2.setOrigin(0, 0);

		this.circle.setData('type', 'deleteWire');
		this.circle.setData('line', line);
		this.circle.setInteractive();

		// Add hover effect
		this.circle.on('pointerover', (e) => this.circle.setFillStyle(0xAA00AA));
		this.circle.on('pointerout', (e) => this.circle.setFillStyle(normalColor));
	}

	// @Override
	destroy()
	{
		this.circle.destroy();
		this.loj1.destroy();
		this.loj2.destroy();
		super.destroy();
	}
}

class Cross extends Phaser.GameObjects.GameObject
{
	/**
	 * 
	 * @param {BaseScene} scene 
	 * @param {number} x x-Position of center point in level coordinates.
	 * @param {number} y y-Position of center point in level coordinates.
	 */
	constructor(scene, x, y, length = 5, lineWidth=1, color = 0xFFAA00)
	{
		super(scene, 'Cross');

		const centerPoint = scene.levelToScreenCoords(x, y);
		this.loj1 = scene.add.line(centerPoint.x, centerPoint.y, -length, -length, length, length, color);
		this.loj2 = scene.add.line(centerPoint.x, centerPoint.y, length, -length, -length, length, color);
		this.loj1.setStrokeStyle(lineWidth, color);
		this.loj2.setStrokeStyle(lineWidth, color);
		this.loj1.setOrigin(0, 0);
		this.loj2.setOrigin(0, 0);
	}

	destroy()
	{
		this.loj1.destroy();
		this.loj2.destroy();
		super.destroy();
	}
}
