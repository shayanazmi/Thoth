import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { constants } from "node:os";

import {
	buildPiArgs,
	buildPiEnv,
	ensureFeynmanCommandShim,
	ensureFeynmanWorkspaceScaffold,
	type PiRuntimeOptions,
	resolvePiPaths,
	toNodeImportSpecifier,
} from "./runtime.js";
import { patchPiRuntimeNodeModules } from "./runtime-patches.js";
import { ensureSupportedNodeVersion } from "../system/node-version.js";
import { resolveAllExecutables } from "../system/executables.js";

export function exitCodeFromSignal(signal: NodeJS.Signals): number {
	const signalNumber = constants.signals[signal];
	return typeof signalNumber === "number" ? 128 + signalNumber : 1;
}

export async function launchPiChat(options: PiRuntimeOptions): Promise<void> {
	ensureSupportedNodeVersion();
	patchPiRuntimeNodeModules(options.appRoot, options.feynmanAgentDir);

	const paths = resolvePiPaths(options.appRoot);
}
