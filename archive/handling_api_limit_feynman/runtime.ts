import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { delimiter, dirname, isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
	BROWSER_FALLBACK_PATHS,
	MERMAID_FALLBACK_PATHS,
	PANDOC_FALLBACK_PATHS,
	resolveExecutable,
	type ResolvedExecutables,
} from "../system/executables.js";
import { getPostHogOtelEnv } from "../telemetry/posthog.js";
import { getPiWebSearchConfigPath } from "./web-access.js";

export type PiRuntimeOptions = {
	appRoot: string;
	workingDir: string;
	sessionDir: string;
	feynmanAgentDir: string;
	feynmanVersion?: string;
	mode?: "text" | "json" | "rpc";
	thinkingLevel?: string;
	explicitModelSpec?: string;
	sessionId?: string;
	resumeRecentSession?: boolean;
	oneShotPrompt?: string;
	initialPrompt?: string;
	preLaunchNotice?: string;
};

export function getFeynmanNpmPrefixPath(feynmanAgentDir: string): string {
	return resolve(dirname(feynmanAgentDir), "npm-global");
}

export function ensureFeynmanWorkspaceScaffold(
	workingDir: string,
	createDirectory: typeof mkdirSync = mkdirSync,
): boolean {
	for (const relPath of [
		"outputs/.plans",
		"outputs/.drafts",
		"papers",
		"notes",
	]) {
		try {
			createDirectory(resolve(workingDir, relPath), { recursive: true });
		} catch (error) {
			const code = (error as NodeJS.ErrnoException).code;
			if (code === "EACCES" || code === "EPERM" || code === "EROFS") {
				return false;
			}
			throw error;
		}
	}
	return true;
}
