class LevelViewScene extends BaseScene
{
	constructor(phaseName = 'LevelViewer')
	{
		super(phaseName);

		this.circuit = null;
		this.circuitGameObjects = [];

		const url = new URL(window.location.href);

		this.showTextAnchors = true; // Show text anchor positions
		this.showClues = true; // Highlight covert gates and switches with random initial state
		this.showIDs = true; // Show the IDs of switches
		this.showWireLen = url.searchParams.has('showWireLen'); // Show the manhattan distance of wires
		this.splittersAlwaysVisible = true;
		this.enableLevelStats = false;
		this.levelPath = null;

		this.state = {
			wireStateVisible: true,
			outputStateVisible: true
		};
	}

	// @Override
	preload()
	{
		this.load.image('arrow_upleft', 'res/images/arrow_upleft.png');
		this.load.image('text', 'res/images/text.png');

		this.load.image('switch_on_2', 'res/elements/switch_on_2.png');
		this.load.image('switch_off_2', 'res/elements/switch_off_2.png');
	}

	// @Override
	createElements(setting)
	{
		// Create error message
		this.errorMessage = this.drawText('Loading ...', 90, 20);

		// Create error highlight
		this.errorHighlight = this.add.circle(0, 0, LevelEditor.elementSelectDistance + 5, 0xFF4422);
		this.errorHighlight.setVisible(false);

		this.customSettings();
		this.loadLevelFromQueryString();

		// Make the screen print friendly
		this.setBrightMode();

		this.registerClickListener('Switch', this.onSwitchClicked);
	}

	/** 
	 * Settings only relevant to the plain LevelViewer
	 */
	customSettings()
	{
		this.showTextAnchors = false;
		this.splittersAlwaysVisible = false;
		this.enableLevelStats = true;

		AniLib.fadeInTime = 0;
	}

	loadLevelFromQueryString()
	{
		const defaultLevelFile = 'assets/levels/elementIntroduction/hre_editor_level.txt';
		const urlParams = new URLSearchParams(window.location.search);
		const basePath = 'assets/levels/differentComplexityLevels/'

		this.levelPath = urlParams.get('level');
		let fullPath = defaultLevelFile;
		if(this.levelPath == null)
			this.levelPath = defaultLevelFile;
		else
			fullPath = basePath + this.levelPath;

		// Create Circuit
		this.loadLevelFromUrl(fullPath);
		this.errorMessage.setText(this.levelPath);
	}

	/**
	 * Request a level file from the server and display it in the editor
	 * @param {string} url e.g. 'assets/levels/elementIntroduction/simple_circuit_copy.txt'
	 */
	loadLevelFromUrl(url)
	{
		console.log(`Requesting level "${url}" from server.`);
		let levelPath = url.split('/');
		let levelName = levelPath[levelPath.length-1];

		Level.getLevelFile((data) =>
		{
			this.loadLevel(levelName, data)
		}, url);
	}

	/**
	 * Display the supplied level data
	 * @param {string} levelName The name of the loaded level used for display or when saving again
	 * @param {string} data The text content of the level file
	 */
	loadLevel(levelName, data)
	{
		try 
		{
			if(this.circuit instanceof Circuit)
			this.circuit.cleanUp();

			if(data.length > (1024*10 - 1) || !data.slice(0, 32).includes('§'))
				throw new Error("Looks like this file is not a level file");

			this.levelFile = new LevelFile(levelName, data);
			this.updateCircuit();

			if(this.enableLevelStats)
				LevelViewScene.printLevelStats(this.levelPath, this.circuit);
		}
		catch(e)
		{
			this.levelFile = new LevelFile();
			this.updateCircuit();

			this.errorMessage.setText('Loading failed: "' + e + '"');
			console.log(e);
		}
	}

	updateCircuit()
	{
		// Investigate this.scene undefined in LogicElement.js:279
		if(!(this instanceof LevelViewScene))
			throw "this is wrong???"

		try 
		{
			// Perform additional checks
			LevelValidator.check(this.levelFile);

			if(this.circuit instanceof Circuit)
			{
				this.circuit.cleanUp();
				this.circuit.file = this.levelFile.fileContent;
				this.circuit.loadElements();
				// Creating a new LogicElementManager, Layouter and LineDrawer inside loadElements() might not be 
				// the most optimized solution but is the simplest
			}
			else
				this.circuit = new Circuit(this, this.levelFile.fileContent, this.splittersAlwaysVisible);

			this.circuit.calculateOutputs();
			this.circuit.wireDrawer.drawWires();

			// Show the wire length if enabled
			if(this.showWireLen)
			{
				for(const wire of this.circuit.wireDrawer.wires)
				{
					const numPoints = wire.getPoints().length;
					const point = wire.getPoints()[Math.max(numPoints - 2, 1)];
					const textPos = BaseScene.levelToScreenCoords(point[0], point[1], this.marginFac);
					const xOffset = 0//(numPoints) > 2 ? 25 : -25;
					this.circuitGameObjects.push(
						this.drawText(
							parseFloat(wire.getLength().toFixed(1)) + 'u', // Hack to properly print float
							textPos.x + xOffset, textPos.y - 20,
							20, LevelViewScene.annotationColor, 'center', true
						)
					);
				}
			}
		}
		catch(error) {
			const errText = 'message' in error ? error.message : error;

			// Show the error message
			this.errorMessage.setText('Routing failed: "' + errText + '"');
			console.error(error);
			let faultyElementID = -1;
			
			// Get the id of the circuit element that raised the error
			if(error instanceof CircuitError)
				faultyElementID = error.elementID;
			else if(typeof error.faultyElement == "number")
				faultyElementID = error.faultyElement;
			
			// Try to find the LevelElement with id `faultyElementID`
			const faultyElement = this.levelFile.getById(faultyElementID);
			if(faultyElement instanceof LevelElement)
			{
				const coords = this.levelToScreenCoords(faultyElement.xPos, faultyElement.yPos);
				this.errorHighlight.setPosition(coords.x, coords.y);
				this.errorHighlight.setVisible(true);
			}
			// Could not find an element with that id
			else
				console.error("Failed to highlight object with error, id " + faultyElementID + " does not exist!");

			return;
		}

		// Display the anchor for the text boxes and images
		for(let c of this.levelFile.parsedLines)
		{
			if(!(c instanceof LevelElement))
				continue;

			const levelPos = LevelViewScene.levelToScreenCoords(c.xPos, c.yPos, this.marginFac);

			if(c.type == 'TextBox' && this.showTextAnchors)
				this.circuitGameObjects.push(new Cross(this, c.xPos, c.yPos, 7, 2, LevelEditor.colorHelperElements));
			else if(c.type == 'Image' && this.showTextAnchors)
				this.circuitGameObjects.push(
					this.drawRect(c.xPos-20, c.yPos-20, 40, 40, LevelEditor.colorHelperElements, 3)
				);
			else if(c.type == 'CovertGate' && this.showClues)
				this.circuitGameObjects.push(
					this.drawText(c.getProperty('actualGate'), levelPos.x, levelPos.y-15, 20, LevelViewScene.annotationColor, 'center', true)
				);
			else if(c.type == 'Switch')
			{
				if(this.showIDs)
					this.drawText(String(c.id), levelPos.x, levelPos.y-45, 30, LevelViewScene.annotationColor, 'center', true)

				if(c.getProperty('isClosed') == 'random' && this.showClues)
					this.circuitGameObjects.push(
						this.drawText('🎲', levelPos.x, levelPos.y, 20, '#ff00ff', 'center', true)
				);
			}
		}
	}

	/**
	 * Called whenever a player is clicking a switch in the circuit.
	 * @param {Phaser.GameObjects.GameObject} gameObject The switch that was clicked
	 */
	onSwitchClicked(gameObject)
	{
		// change switch state
		gameObject.getData('element').switchClicked();

		// Calculate outputs and depending on the difficulty visualize level state
		this.updateLevelState(false);
	}

	/**
	 * Update the internal state of the level and depending on the difficulty display the state to the player.
	 * @param {boolean} confirmClick True if the triggering event is a confirm click.
	 */
	updateLevelState(confirmClick)
	{		
		// Update the level ui
		this.circuit.setShowState(this.state.wireStateVisible, this.state.outputStateVisible);
		this.circuit.calculateOutputs();
		this.circuit.wireDrawer.drawWires();
	}
	
	/**
	 * 
	 * @param {number} x1 X-position of the top left corner in level coordinates.
	 * @param {number} y1 Y-position of the top left corner in level coordinates.
	 * @param {number} width 
	 * @param {number} height 
	 * @param {number} color 
	 * @param {number} lineWidth 
	 * @param {number} alpha 
	 * @returns 
	 */
	drawRect(x1, y1, width, height, color, lineWidth=1, alpha=1)
	{
		const begin = LevelEditor.levelToScreenCoords(x1, y1, this.marginFac);
		const end = LevelEditor.levelToScreenCoords(width + x1, height + y1, this.marginFac);

		let rect = this.add.rectangle(begin.x, begin.y, end.x - begin.x, end.y - begin.y);
		rect.setOrigin(0, 0);
		rect.setStrokeStyle(lineWidth, color, alpha);

		return rect;
	}

	/**
	 * 
	 * @param {string} str The text to render
	 * @param {number} x X-coordinate in screen space.
	 * @param {number} y Y-coordinate in screen space.
	 * @param {number} size Font size
	 * @param {*} color Hex code of the color
	 * @returns 
	 */
	drawText(str, x, y, size = 20, color = '#F8B170', align = 'left', toFront = false)
	{
		const h_align = {left: 0, right: 1, center: 0.5};

		var txtObject = this.add.text(x, y, str, textStyle);
		txtObject.setFontSize(size);
		txtObject.setStyle({ color: color });
		txtObject.setWordWrapWidth(config.width - y - 200);

		txtObject.setOrigin(h_align[align], txtObject.originY);

		if(toFront)
			txtObject.setDepth(200);

		return txtObject;
	}

	/**
	 * Watch your eyes, the screen is about to leave the dark mode!
	 */
	setBrightMode()
	{
		this.cameras.main.setBackgroundColor(0xffffff);
		LineDrawer.wireOnColor = 0xaacc00;
		LineDrawer.wireOffColor = 0x333333;

		Switch.imageOpen = 'switch_off_2';
		Switch.imageClosed = 'switch_on_2';

		TextBox.defaultTextColor = '#111166';
	}

	/**
	 * Print some numerical statistics like the number of gates to the console.
	 * 
	 * The hamming distance of the switches is calculated from off position.
	 * @param {string} path The name of the level.
	 * @param {Circuit} circuit The Circuit game object to gather the stats from.
	 */
	static printLevelStats(path, circuit)
	{
		const numSwitches = circuit.getSwitches().length;

		let output = {
			name: path,
			numSwitches: numSwitches,
			numOutputs: circuit.getBulbs().length + circuit.getDangerSigns().length,
			numGates: circuit.elementsManager.getNumGates(),
			numAND: circuit.elementsManager.getAndGates().length,
			numOR: circuit.elementsManager.getOrGates().length,
			numNOT: circuit.elementsManager.getInverters().length,
			numObfuscated: circuit.elementsManager.covertGates.length,
			timeLimit: circuit.elementsManager.timeLimit,
			numSwitchesRand: circuit.getSwitches().filter(v => v._switchStateInitial == "random").length,
			solutions: circuit.calculateAllSolutions(false, new Array(numSwitches).fill(0))
		}

		console.log(JSON.stringify(output));
	}
}

LevelViewScene.annotationColor = '#3498db'