import { connectToDatabase } from '@/database/mongoose';
import { Watchlist } from '@/database/models/watchlist.model';

/** Internal Inngest service. This module is not exposed as a Next server action. */
export async function getAllUsersForNewsEmail() {
  const mongoose = await connectToDatabase();
  const db = mongoose.connection.db;
  if (!db) throw new Error('Mongoose connection not connected');

  const users = await db.collection('user').find(
    { email: { $exists: true, $ne: null } },
    { projection: { _id: 1, id: 1, email: 1, name: 1 } },
  ).toArray();

  return users
    .filter((user: { email?: string; name?: string }) => user.email && user.name)
    .map((user: { id?: string; _id?: { toString(): string }; email?: string; name?: string }) => ({
      id: user.id || user._id?.toString() || '',
      email: user.email as string,
      name: user.name as string,
    }));
}

export async function getWatchlistSymbolsByEmail(email: string): Promise<string[]> {
  if (!email) return [];
  const mongoose = await connectToDatabase();
  const db = mongoose.connection.db;
  if (!db) throw new Error('MongoDB connection not found');

  const user = await db.collection('user').findOne({ email }) as {
    _id?: unknown;
    id?: string;
  } | null;
  if (!user) return [];
  const userId = user.id || String(user._id || '');
  if (!userId) return [];
  const items = await Watchlist.find({ userId }, { symbol: 1 }).lean();
  return items.map((item) => String(item.symbol));
}
