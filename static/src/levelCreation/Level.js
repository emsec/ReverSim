class Level
{
	/**
	 * 
	 * @param {string} levelStr The raw level file string. Please note that the encoding was Windows-1252 and is now configured in `config.LEVEL_ENCODING`.
	 * @param {string} difficulty Either EASY (power is always visible), MEDIUM (power is only shown when probing) or HARD (power is never shown).
	 * @param {string} phase 
	 * @param {Phaser.Scene} scene The parent scene for this object. Not used by this class but it is passed to some objects.
	 */
	constructor(levelStr, difficulty, phase, scene)
	{
		this.stats = {
			"switchClickCtr": 0,
			"confirmClickCtr": 0,
			"simulateCtr": 0,
			"score": scoreValues.startValue
		};

		this.phase = phase;
		this.difficulty = difficulty;
		this.circuit = new Circuit(scene, levelStr);
		this.showState = false;
		
		this.resetInitialSwitchStates();
	}

	/**
	 * Save the current switch states as the initial switch states.
	 * Also updates the minimal hamming distance.
	 */
	resetInitialSwitchStates() 
	{
		this.initialSwitchStates = this.circuit.getSwitches().map(s => s.switchState);
		this.minimalHammingDistance = this.calculateOptimum();
	}

	/**
	 * Calculate the new score based upon the value specified in scoreValues.
	 * @param {string} operationName The name of the operation that was performed: switchClick / simulate / wrongSolution
	 */
	updateScore(operationName)
	{
		let value = scoreValues[operationName];
		if(value === undefined)
		{
			console.error('The scoreboard does not know the value for ' + operationName + ', leaving scoreboard unchanged.');
			return
		}

		const penaltyMultiplier = 'penaltyMultiplier' in scoreValues ? scoreValues['penaltyMultiplier'] : 1;
		
		// Allow incremental punishment for multiple wrong confirm clicks, see GameConfig.md#scorevalues
		if(operationName == 'wrongSolution')
			value = value * (1 + penaltyMultiplier * (this.stats.confirmClickCtr - 1))
		
		// Clip the value to the minimum score
		this.stats.score = Math.max(scoreValues.minimumScore, this.stats.score + value);

		// Display a small animation to visualize the points
		if(Math.abs(scoreValues[operationName]) > 0.0001) // Don't display a +0
		{
			let differenceText = AddText.addText(this.circuit.scene, 1080, 20, (scoreValues[operationName] > 0 ? '+' : '') + value, false);
			differenceText.setFontSize(20);
			differenceText.setStyle({ color: '#FFAA00', align: 'center' });
			AniLib.disappear(differenceText, this.circuit.scene);
		}
	}

	/**
	 * Calculate the minimum number of switch clicks possible.
	 * @returns {number} Minimal number of switch clicks possible.
	 */
	calculateOptimum()
	{
		const result = this.circuit.calculateAllSolutions(true, this.initialSwitchStates);

		//console.log('min hd: ' + result.minHD.toString())
		return result.minHD;
	}

	/**
	 * Update the outputs to display the current input state
	 */
	calculateOutputs()
	{
		this.circuit.calculateOutputs();
	}

	/**
	 * Set if the switches can be clicked.
	 * @param {boolean} state True if the switches can be clicked, false otherwise.
	 */
	setSwitchesInteractive(state)
	{
		this.circuit.setInteractive(state);
	}

	/**
	 * Get if the level was solved correctly or not. 
	 * A level is called solved if all light bulbs are on and all danger signs are off.
	 * @returns {number} 1 if the level was solved correctly and 0 if not.
	 */
	getSolvingState()
	{
		// test wether all bulbs are turned on
		var state = 1;
		for(const endPoint of this.circuit.elementsManager.getLightBulbs())
		{
			state *= state * endPoint.getOutputState();
		}
		if(state != 1) return 0;

		// test wether all danger signs are turned off
		state = 0;
		for(const endPoint of this.circuit.elementsManager.getDangerSigns())
		{
			state += state + endPoint.getOutputState();
		}
		if(state != 0) return 0;

		// all danger signs are turned off and all bulbs are turned on
		return 1;
	}

	/**
	 * Get the phase of this level
	 * @returns {string} 
	 */
	getPhase()
	{
		return this.phase;
	}

	/**
	 * Get the current difficulty set for this level.
	 * @returns {string} Either EASY (power is always visible), MEDIUM (power is only shown when probing) or HARD (power is never shown).
	 */
	getDifficulty()
	{
		return this.difficulty;
	}

	/**
	 * The highest score the player can archive
	 * @returns The minimum amount of switch clicks times the penalty for a single switch click. If the difficulty is medium it will also add a simulate penalty for each covert gate present in the circuit.
	 */
	getBestScorePossible()
	{
		return scoreValues.startValue 
			+ this.minimalHammingDistance * scoreValues.switchClick 
			+ (this.circuit.scene.getSimulateButtonEnabled() ? this.circuit.elementsManager.covertGates.length * scoreValues.simulate : 0);
	}

	/**
	 * Get the time limit configured for this level in seconds.
	 * @returns A fractional number in seconds. 0 means no time limit.
	 */
	getTimeLimit()
	{
		return this.circuit.elementsManager.timeLimit;
	}

	/**
	 * Get a level file from the server
	 * @param {*} callback Called after the level is received.
	 * @param {string} url The url of the level. 
	 * @param {*} key ??? Probably there to pass around a parameter
	 */
	static getLevelFile(callback, url, key)
	{
		Rq.get(url, (data, resCode, getResponseHeader) => {
			var responseType = getResponseHeader('type');
			callback(data, responseType, key);
		});
	}
}

/**
 * CONFIG: The value of each operation for the scoreboard.
 * 
 * startValue: The value the score gets initialized to. Useful when the operations are subtracted from the score (negative score)
 * minimumScore: The smallest value the score will ever reach. Use a very big negative number if you don't wish to use this feature
 * switchClick: The penalty for clicking a switch
 * simulate: The penalty for using the simulate button
 * wrongSolution: The penalty for clicking confirm witch a wrong solution
 * correctSolution: The penalty for clicking the confirm button with the correct solution
 * 
 */
const scoreValues = gamerules.scoreValues