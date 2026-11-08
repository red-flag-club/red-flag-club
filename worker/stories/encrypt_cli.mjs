// Test helper: encrypt a JSON object exactly as the Worker does.
//   node encrypt_cli.mjs '<json>' <base64 SPKI public key>
import { encrypt } from "./index.js";
console.log(JSON.stringify(await encrypt(JSON.parse(process.argv[2]), process.argv[3])));
