export type UserRole="user"|"admin";
export type SubscriptionPlan="free"|"pro"|"enterprise";
export interface ApiError{code:string;message:string;requestId?:string}
export interface WsEvent<T=unknown>{type:string;timestamp:number;data:T}
